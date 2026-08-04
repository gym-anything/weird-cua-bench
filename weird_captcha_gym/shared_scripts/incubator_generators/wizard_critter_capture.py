from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "wizard_critter_capture"
ARENA_WIDTH = 840
ARENA_HEIGHT = 430
X_MIN = 28
X_MAX = 812
Y_MIN = 34
Y_MAX = 366
TICK_MS = 70
TIME_LIMIT_TICKS = 150
FREEZE_ENERGY_TICKS = 24
MIN_FREEZE_TICKS = 10
SOLVER_FREEZE_TICKS = 12
NET_COUNT = 4
NET_FLIGHT_TICKS = 12
CREATURE_RADIUS_X10 = 160
NET_RADIUS_X10 = 150
COLLISION_RADIUS_X10 = CREATURE_RADIUS_X10 + NET_RADIUS_X10
PROJECTILE_ORIGIN = (4200, 4100)
VARIANT_COUNT = 91_768_320_000

PALETTES = (
    {"name": "moonlit_vellum", "ink": "#273449", "paper": "#e7dfc5", "magic": "#33c7b4", "danger": "#d35a68"},
    {"name": "mauve_eclipse", "ink": "#35283f", "paper": "#e8d8cf", "magic": "#7fc9ff", "danger": "#e6618f"},
    {"name": "lichen_codex", "ink": "#29382f", "paper": "#ddd9bd", "magic": "#8acb78", "danger": "#df6a54"},
    {"name": "cobalt_almanac", "ink": "#1c3650", "paper": "#dedbc9", "magic": "#52d9d0", "danger": "#e37c55"},
)
GLYPHS = ("crescent", "trident", "hourglass", "comet", "thorn", "lantern")
HORNS = ("curl", "fork", "spire", "leaf")
TAILS = ("ribbon", "tuft", "fork", "fan")
FAMILY_COLORS = (
    ("#d8a4ff", "#532d69", "#fbdd78"),
    ("#89d7c2", "#234e4f", "#ffd77b"),
    ("#f09a8d", "#6b3344", "#d7f58b"),
    ("#8ebbf5", "#263f70", "#ffbe75"),
)

OCCLUDERS = (
    {"id": "archive-curtain", "x": 650, "y": 72, "width": 142, "height": 176, "kind": "curtain"},
    {"id": "orrery-tower", "x": 372, "y": 112, "width": 130, "height": 178, "kind": "tower"},
    {"id": "vapor-cabinet", "x": 154, "y": 226, "width": 176, "height": 122, "kind": "vapor"},
)
PORTALS = (
    {"id": "west-moon", "x": X_MIN, "y": 200, "radius": 30},
    {"id": "east-moon", "x": X_MAX, "y": 200, "radius": 30},
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _critter_id(seed: str, index: int) -> str:
    token = hashlib.sha256(f"{seed}|critter|{index}".encode("utf-8")).hexdigest()[:8]
    return f"familiar-{token}"


def _trunc_div(value: int, divisor: int) -> int:
    return int(value / divisor)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _inside_occluder(x10: int, y10: int) -> bool:
    x, y = x10 / 10, y10 / 10
    return any(
        int(item["x"]) <= x <= int(item["x"]) + int(item["width"])
        and int(item["y"]) <= y <= int(item["y"]) + int(item["height"])
        for item in OCCLUDERS
    )


def _lure_vector(critter: dict[str, Any], lure: tuple[int, int]) -> tuple[int, int]:
    dx = lure[0] - int(critter["x10"])
    dy = lure[1] - int(critter["y10"])
    ax = 10 if dx > 250 else -10 if dx < -250 else 0
    ay = 7 if dy > 220 else -7 if dy < -220 else 0
    return ax, ay


def _step_critter(critter: dict[str, Any], lure: tuple[int, int], frozen: bool) -> dict[str, Any]:
    next_critter = dict(critter)
    ax, ay = _lure_vector(next_critter, lure)
    next_critter["vx10"] = _clamp(int(next_critter["vx10"]) + ax, -74, 74)
    next_critter["vy10"] = _clamp(int(next_critter["vy10"]) + ay, -54, 54)
    divisor = 3 if frozen else 1
    next_critter["x10"] = int(next_critter["x10"]) + _trunc_div(int(next_critter["vx10"]), divisor)
    next_critter["y10"] = int(next_critter["y10"]) + _trunc_div(int(next_critter["vy10"]), divisor)

    minimum_y, maximum_y = Y_MIN * 10, Y_MAX * 10
    if int(next_critter["y10"]) < minimum_y:
        next_critter["y10"] = minimum_y + (minimum_y - int(next_critter["y10"]))
        next_critter["vy10"] = abs(int(next_critter["vy10"]))
    elif int(next_critter["y10"]) > maximum_y:
        next_critter["y10"] = maximum_y - (int(next_critter["y10"]) - maximum_y)
        next_critter["vy10"] = -abs(int(next_critter["vy10"]))

    minimum_x, maximum_x = X_MIN * 10, X_MAX * 10
    if int(next_critter["x10"]) > maximum_x:
        next_critter["x10"] = minimum_x + (int(next_critter["x10"]) - maximum_x)
        next_critter["portal_count"] = int(next_critter.get("portal_count", 0)) + 1
    elif int(next_critter["x10"]) < minimum_x:
        next_critter["x10"] = maximum_x - (minimum_x - int(next_critter["x10"]))
        next_critter["portal_count"] = int(next_critter.get("portal_count", 0)) + 1
    next_critter["occluded"] = _inside_occluder(int(next_critter["x10"]), int(next_critter["y10"]))
    if next_critter["occluded"]:
        next_critter["occluded_ticks"] = int(next_critter.get("occluded_ticks", 0)) + 1
    return next_critter


def _snapshot(critters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item["id"]),
            "x10": int(item["x10"]),
            "y10": int(item["y10"]),
            "vx10": int(item["vx10"]),
            "vy10": int(item["vy10"]),
            "portal_count": int(item.get("portal_count", 0)),
            "occluded": bool(item.get("occluded", False)),
            "occluded_ticks": int(item.get("occluded_ticks", 0)),
        }
        for item in critters
    ]


def _baseline_states(
    critters: list[dict[str, Any]],
    lure: tuple[int, int],
    *,
    freeze_ticks: int = SOLVER_FREEZE_TICKS,
    ticks: int = 130,
) -> list[list[dict[str, Any]]]:
    state = copy.deepcopy(critters)
    states = [state]
    for tick in range(1, ticks + 1):
        frozen = tick <= freeze_ticks
        state = [_step_critter(item, lure, frozen) for item in state]
        states.append(state)
    return states


def _projectile_point(aim: tuple[int, int], age: int, flight_ticks: int = NET_FLIGHT_TICKS) -> tuple[int, int]:
    origin_x, origin_y = PROJECTILE_ORIGIN
    return (
        origin_x + _trunc_div((aim[0] - origin_x) * age, flight_ticks),
        origin_y + _trunc_div((aim[1] - origin_y) * age, flight_ticks),
    )


def _first_projectile_hit(
    states: list[list[dict[str, Any]]],
    shot_tick: int,
    aim: tuple[int, int],
    flight_ticks: int = NET_FLIGHT_TICKS,
) -> tuple[str | None, int | None]:
    radius_squared = COLLISION_RADIUS_X10 * COLLISION_RADIUS_X10
    for age in range(1, flight_ticks + 1):
        projectile_x, projectile_y = _projectile_point(aim, age, flight_ticks)
        for critter in states[shot_tick + age]:
            dx = projectile_x - int(critter["x10"])
            dy = projectile_y - int(critter["y10"])
            if dx * dx + dy * dy <= radius_squared:
                return str(critter["id"]), shot_tick + age
    return None, None


def _intercept_plans(
    critters: list[dict[str, Any]],
    target_id: str,
    lure: tuple[int, int],
    *,
    freeze_ticks: int = SOLVER_FREEZE_TICKS,
    portal_transitions: int = 1,
    occluded_ticks: int = 3,
    flight_ticks: int = NET_FLIGHT_TICKS,
    time_limit_ticks: int = TIME_LIMIT_TICKS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    states = _baseline_states(critters, lure, freeze_ticks=freeze_ticks)
    target_plans: list[dict[str, Any]] = []
    decoy_plans: list[dict[str, Any]] = []
    maximum_shot_tick = min(85, time_limit_ticks - flight_ticks)
    for shot_tick in range(freeze_ticks + 4, maximum_shot_tick + 1):
        future = {str(item["id"]): item for item in states[shot_tick + flight_ticks]}
        target = future[target_id]
        aim = (round(int(target["x10"]) / 10) * 10, round(int(target["y10"]) / 10) * 10)
        hit_id, hit_tick = _first_projectile_hit(states, shot_tick, aim, flight_ticks)
        target_now = next(item for item in states[shot_tick] if str(item["id"]) == target_id)
        current_aim = (round(int(target_now["x10"]) / 10) * 10, round(int(target_now["y10"]) / 10) * 10)
        current_hit_id, _current_hit_tick = _first_projectile_hit(states, shot_tick, current_aim, flight_ticks)
        target_at_hit = next(item for item in states[int(hit_tick or shot_tick)] if item["id"] == target_id)
        if (
            hit_id == target_id
            and current_hit_id != target_id
            and hit_tick is not None
            and int(target_at_hit.get("portal_count", 0)) >= portal_transitions
            and int(target_at_hit.get("occluded_ticks", 0)) >= occluded_ticks
        ):
            target_plans.append(
                {
                    "shot_tick": shot_tick,
                    "aim": [aim[0] // 10, aim[1] // 10],
                    "expected_hit_tick": hit_tick,
                }
            )
        for decoy_id in (str(item["id"]) for item in critters if str(item["id"]) != target_id):
            decoy = future[decoy_id]
            decoy_aim = (round(int(decoy["x10"]) / 10) * 10, round(int(decoy["y10"]) / 10) * 10)
            decoy_hit_id, decoy_hit_tick = _first_projectile_hit(states, shot_tick, decoy_aim, flight_ticks)
            if decoy_hit_id == decoy_id and decoy_hit_tick is not None:
                decoy_plans.append(
                    {
                        "critter_id": decoy_id,
                        "shot_tick": shot_tick,
                        "aim": [decoy_aim[0] // 10, decoy_aim[1] // 10],
                        "expected_hit_tick": decoy_hit_tick,
                    }
                )
                break
        if len(target_plans) >= 10 and len(decoy_plans) >= 4:
            break
    return target_plans, decoy_plans


def _appearance(rng: random.Random, index: int, family: tuple[str, str, str], target: dict[str, Any] | None = None) -> dict[str, Any]:
    if target is None:
        return {
            "body": family[0],
            "shadow": family[1],
            "accent": family[2],
            "glyph": GLYPHS[rng.randrange(len(GLYPHS))],
            "horn": HORNS[rng.randrange(len(HORNS))],
            "tail": TAILS[rng.randrange(len(TAILS))],
            "eyes": 1 + rng.randrange(3),
            "spots": 2 + rng.randrange(4),
        }
    related = dict(target)
    mutation = index % 4
    if mutation == 0:
        related["glyph"] = GLYPHS[(GLYPHS.index(str(target["glyph"])) + 1) % len(GLYPHS)]
    elif mutation == 1:
        related["horn"] = HORNS[(HORNS.index(str(target["horn"])) + 1) % len(HORNS)]
    elif mutation == 2:
        related["tail"] = TAILS[(TAILS.index(str(target["tail"])) + 1) % len(TAILS)]
    else:
        related["eyes"] = 1 + (int(target["eyes"]) % 3)
    return related


def _signature(appearance: dict[str, Any]) -> str:
    encoded = "|".join(str(appearance[key]) for key in sorted(appearance))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    if condition is not None and not isinstance(condition, dict):
        raise ValueError("wizard control condition must be an object")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    try:
        difficulty = int(condition["difficulty"]) if condition is not None else 4
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("wizard control condition has no valid difficulty") from exc
    critter_count = int(parameters.get("critter_count", 5))
    minimum_freeze_ticks = int(parameters.get("minimum_freeze_ticks", MIN_FREEZE_TICKS))
    freeze_energy_ticks = int(parameters.get("freeze_energy_ticks", FREEZE_ENERGY_TICKS))
    target_portal_transitions = int(parameters.get("target_portal_transitions", 1))
    target_occluded_ticks = int(parameters.get("target_occluded_ticks", 3))
    net_count = int(parameters.get("net_count", NET_COUNT))
    time_limit_ticks = int(parameters.get("time_limit_ticks", TIME_LIMIT_TICKS))
    target_spawn = str(parameters.get("target_spawn", "covered"))
    target_reference_visibility = str(parameters.get("target_reference_visibility", "persistent"))
    solver_freeze_ticks = int(parameters.get("solver_freeze_ticks", SOLVER_FREEZE_TICKS))
    interaction = str((condition or {}).get("interaction") or "full")
    if not 1 <= critter_count <= 5:
        raise ValueError("wizard critter_count must be between one and five")
    if not 0 <= minimum_freeze_ticks <= freeze_energy_ticks:
        raise ValueError("wizard freeze requirement exceeds its energy budget")
    if not minimum_freeze_ticks <= solver_freeze_ticks <= freeze_energy_ticks:
        raise ValueError("wizard solver freeze plan is outside the freeze budget")
    if target_portal_transitions not in {0, 1} or target_occluded_ticks < 0:
        raise ValueError("wizard tracking requirements are unsupported")
    if not 1 <= net_count <= 6 or not 30 <= time_limit_ticks <= 240:
        raise ValueError("wizard net or time settings are outside supported limits")
    if target_spawn not in {"covered", "visible"}:
        raise ValueError("wizard target spawn must be covered or visible")
    if target_reference_visibility not in {"persistent", "preview_only"}:
        raise ValueError("wizard target reference visibility is unsupported")
    if interaction not in {"simplified", "full"}:
        raise ValueError("wizard interaction must be simplified or full")

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    task_id = str(task.get("id") or "wizard_critter_capture_seed_0001@0.1")
    condition_token = "" if condition is None or difficulty == 4 else f"|difficulty-{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|interception-v1{condition_token}".encode("utf-8")).hexdigest()[:14]
    palette = copy.deepcopy(rng.choice(PALETTES))
    family = rng.choice(FAMILY_COLORS)
    target_index = rng.randrange(critter_count)
    target_appearance = _appearance(rng, target_index, family)

    # The original L4 familiar begins behind the eastern archive curtain,
    # emerges, and crosses a real portal before a valid interception window.
    # The lower profiles can instead begin in open space; the L4 branch keeps
    # its historical random draws and resulting world unchanged.
    if target_spawn == "covered":
        target_state = {
            "x10": rng.randint(6980, 7240),
            "y10": rng.randint(1120, 2020),
            "vx10": rng.randint(48, 59),
            "vy10": rng.randint(-14, 16),
        }
    else:
        target_state = {
            "x10": rng.randint(5400, 5900),
            "y10": rng.randint(560, 1000),
            "vx10": rng.randint(34, 43),
            "vy10": rng.randint(8, 22),
        }
    decoy_states = (
        (rng.randint(480, 1300), rng.randint(620, 1700), rng.randint(38, 55), rng.randint(13, 31)),
        (rng.randint(3320, 4500), rng.randint(620, 1560), rng.randint(-52, -38), rng.randint(12, 32)),
        (rng.randint(1840, 3000), rng.randint(2720, 3440), rng.randint(34, 49), rng.randint(-30, -13)),
        (rng.randint(5200, 6200), rng.randint(2760, 3480), rng.randint(-50, -36), rng.randint(-27, -11)),
    )
    critters: list[dict[str, Any]] = []
    decoy_cursor = 0
    for index in range(critter_count):
        critter_id = _critter_id(seed, index)
        if index == target_index:
            state = target_state
            appearance = target_appearance
        else:
            values = decoy_states[decoy_cursor]
            decoy_cursor += 1
            state = {"x10": values[0], "y10": values[1], "vx10": values[2], "vy10": values[3]}
            appearance = _appearance(rng, index, family, target_appearance)
        critters.append(
            {
                "id": critter_id,
                "label": f"FAMILIAR {chr(65 + index)}-{rng.randint(10, 99)}",
                "appearance": appearance,
                **state,
                "portal_count": 0,
                "occluded": _inside_occluder(int(state["x10"]), int(state["y10"])),
                "occluded_ticks": 0,
            }
        )
    target_id = str(critters[target_index]["id"])
    lure_candidates = [
        (
            round(rng.randint(7660, 7940) / 10) * 10,
            round(_clamp(int(target_state["y10"]) + rng.randint(-380, 380), 760, 2600) / 10) * 10,
        ),
        (7860, int(target_state["y10"])),
        (7600, 1800),
    ]
    solver_plans: list[dict[str, Any]] = []
    decoy_plans: list[dict[str, Any]] = []
    lure = lure_candidates[0]
    for candidate in lure_candidates:
        candidate_targets, candidate_decoys = _intercept_plans(
            critters,
            target_id,
            candidate,
            freeze_ticks=solver_freeze_ticks,
            portal_transitions=target_portal_transitions,
            occluded_ticks=target_occluded_ticks,
            time_limit_ticks=time_limit_ticks,
        )
        if candidate_targets:
            lure = candidate
            solver_plans = candidate_targets
            decoy_plans = candidate_decoys
            break
    if len(solver_plans) < 3:
        raise AssertionError(f"seed {seed!r} has no robust target interception window")

    target_cue = {
        "appearance": copy.deepcopy(target_appearance),
        "signature": _signature(target_appearance),
        "mnemonic": f"{target_appearance['glyph']} rune · {target_appearance['horn']} horns · {target_appearance['eyes']} eyes",
    }
    requirements = {
        "preview_min_ms": 900,
        "minimum_freeze_ticks": minimum_freeze_ticks,
        "target_portal_transitions": target_portal_transitions,
        "target_occluded_ticks": target_occluded_ticks,
        "net_count": net_count,
        "freeze_energy_ticks": freeze_energy_ticks,
        "time_limit_ticks": time_limit_ticks,
        "critter_count": critter_count,
        "target_reference_visibility": target_reference_visibility,
    }
    arena = {
        "width": ARENA_WIDTH,
        "height": ARENA_HEIGHT,
        "tick_ms": TICK_MS,
        "x_min": X_MIN,
        "x_max": X_MAX,
        "y_min": Y_MIN,
        "y_max": Y_MAX,
        "projectile_origin": [PROJECTILE_ORIGIN[0] // 10, PROJECTILE_ORIGIN[1] // 10],
        "net_flight_ticks": NET_FLIGHT_TICKS,
        "creature_radius_x10": CREATURE_RADIUS_X10,
        "net_radius_x10": NET_RADIUS_X10,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language")
        or "Remember the marked familiar, bend its path with one lure, spend freeze carefully, then lead a traveling net through cover and portals.",
        "submit_label": "INTERCEPT FAMILIAR",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {
            "name": "wizard_interception_observatory_v1",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "palette/family/identity/kinematics/lure/intercept construction space",
        },
        "palette": palette,
        "arena": arena,
        "portals": [dict(item) for item in PORTALS],
        "occluders": [dict(item) for item in OCCLUDERS],
        "critters": copy.deepcopy(critters),
        "target_cue": target_cue,
        "requirements": requirements,
        "rules": [
            (
                "The marked familiar reference remains visible during the hunt."
                if target_reference_visibility == "persistent"
                else "The marked familiar reference shutters after the opening observation window."
            ),
            "Arm one lure and place it in the arena; its well bends every familiar's velocity.",
            (
                "Hold F to spend finite freeze energy. Nets travel for twelve clock ticks, so lead the target."
                if interaction == "full"
                else "Use SPEND REQUIRED FREEZE to spend finite freeze energy. Nets travel for twelve clock ticks, so lead the target."
            ),
            "A decoy consumes a net. Capture requires a lure, meaningful freeze, cover tracking, and a real target intersection.",
        ],
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": palette,
        "arena": arena,
        "portals": public_state["portals"],
        "occluders": public_state["occluders"],
        "critters": copy.deepcopy(critters),
        "target_cue": target_cue,
        "requirements": requirements,
        "target_id": target_id,
        "solver_lure": [lure[0] // 10, lure[1] // 10],
        "solver_freeze_ticks": solver_freeze_ticks,
        "solver_plans": solver_plans,
        "decoy_plans": decoy_plans,
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert target_cue["signature"] == _signature(next(item for item in critters if item["id"] == target_id)["appearance"])
    assert target_id not in str(public_state.get("target_cue"))
    return public_state, ground_truth
