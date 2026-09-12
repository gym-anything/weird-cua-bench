"""Seeded voxel-beam disentanglement for Timber Knot Release.

The generator constructs a compact collision-free assembly by reversing a
sequence of legal one-cell insertions.  The hidden insertion order is not
sent to the browser; the browser and grader only receive the visible voxel
solids and their permitted translation axes.
"""
from __future__ import annotations

import copy
import hashlib
import random
from typing import Any, Iterable

MECHANIC_ID = "timber_knot_release"
AXES = ("x", "y", "z")
AXIS_INDEX = {name: index for index, name in enumerate(AXES)}
PROFILES = {
    1: {"piece_count": 3, "beam_length": 3, "notch_density": 0, "extraction_steps": 5, "visual_decoys": 0},
    2: {"piece_count": 3, "beam_length": 4, "notch_density": 1, "extraction_steps": 6, "visual_decoys": 1},
    3: {"piece_count": 4, "beam_length": 4, "notch_density": 1, "extraction_steps": 6, "visual_decoys": 1},
    4: {"piece_count": 5, "beam_length": 5, "notch_density": 2, "extraction_steps": 7, "visual_decoys": 2},
    5: {"piece_count": 6, "beam_length": 5, "notch_density": 2, "extraction_steps": 8, "visual_decoys": 3},
}
COLORS = ["ochre", "vermilion", "indigo", "moss", "saffron", "plum"]


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, int, dict[str, int]]:
    condition = copy.deepcopy(task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition"))
    level = int((condition or {}).get("difficulty") or 3)
    if level not in PROFILES:
        raise ValueError(f"unsupported Timber Knot Release level {level}")
    params = dict(PROFILES[level])
    params.update((condition or {}).get("difficulty_parameters") or {})
    expected = set(PROFILES[level])
    if set(params) != expected or any(int(params[key]) < 0 for key in ("notch_density", "visual_decoys")):
        raise ValueError("malformed Timber Knot Release profile")
    if not 3 <= int(params["piece_count"]) <= 6 or not 3 <= int(params["beam_length"]) <= 5:
        raise ValueError("unsupported Timber Knot Release dimensions")
    if not 4 <= int(params["extraction_steps"]) <= 9:
        raise ValueError("unsupported Timber Knot Release extraction length")
    return condition, level, {key: int(value) for key, value in params.items()}


def _cells_for(index: int, length: int, shoulders: int) -> list[list[int]]:
    long_axis = (index + 1) % 3
    side_a = (long_axis + 1) % 3
    side_b = (long_axis + 2) % 3
    cells: list[tuple[int, int, int]] = []
    for along in range(length):
        cell = [0, 0, 0]
        cell[long_axis] = along
        cells.append(tuple(cell))
    if shoulders:
        for along, side, amount in ((1, side_a, 1), (length - 2, side_b, 1)):
            cell = [0, 0, 0]
            cell[long_axis] = along
            cell[side] = amount
            if tuple(cell) not in cells:
                cells.append(tuple(cell))
    return [list(cell) for cell in cells]


def _translated(cells: Iterable[Iterable[int]], offset: Iterable[int]) -> set[tuple[int, int, int]]:
    origin = tuple(int(value) for value in offset)
    return {tuple(int(cell[index]) + origin[index] for index in range(3)) for cell in cells}


def _overlap(a_cells: Iterable[Iterable[int]], a_offset: Iterable[int], b_cells: Iterable[Iterable[int]], b_offset: Iterable[int]) -> bool:
    return bool(_translated(a_cells, a_offset) & _translated(b_cells, b_offset))


def _swept_clear(cells: list[list[int]], old: list[int], new: list[int], others: list[dict[str, Any]]) -> bool:
    """Check the full continuous unit-cell sweep, not only its endpoints."""
    moved = _translated(cells, old)
    deltas = [int(new[i]) - int(old[i]) for i in range(3)]
    axis = next((index for index, value in enumerate(deltas) if value), None)
    if axis is None or any(value not in (-1, 0, 1) for value in deltas) or sum(bool(value) for value in deltas) != 1:
        return False
    for other in others:
        fixed = _translated(other["voxels"], other["offset"])
        for a in moved:
            for b in fixed:
                perpendicular = all(a[k] == b[k] for k in range(3) if k != axis)
                if not perpendicular:
                    continue
                start = a[axis]
                finish = a[axis] + deltas[axis]
                low, high = sorted((start, finish))
                # Positive volume overlap with the unit cube [b,b+1].
                if max(low, b[axis]) < min(high + 1, b[axis] + 1):
                    return False
    return True


def _packed_clear(pieces: list[dict[str, Any]]) -> bool:
    for index, piece in enumerate(pieces):
        if _overlap(piece["voxels"], piece["offset"], [], [0, 0, 0]):
            return False
        for other in pieces[index + 1:]:
            if _overlap(piece["voxels"], piece["offset"], other["voxels"], other["offset"]):
                return False
    return True


def _build_candidate(rng: random.Random, params: dict[str, int]) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]] | None:
    count, length, shoulders, steps = (params[key] for key in ("piece_count", "beam_length", "notch_density", "extraction_steps"))
    for _ in range(1800):
        pieces: list[dict[str, Any]] = []
        cells = [_cells_for(index, length, shoulders) for index in range(count)]
        for index in range(count):
            placed = False
            for _attempt in range(80):
                offset = [rng.randint(-3, 2), rng.randint(-3, 2), rng.randint(-3, 2)]
                candidate = {"id": f"beam-{index + 1}", "voxels": cells[index], "offset": offset}
                if all(not _overlap(candidate["voxels"], offset, old["voxels"], old["offset"]) for old in pieces):
                    pieces.append(candidate)
                    placed = True
                    break
            if not placed:
                break
        if len(pieces) != count:
            continue
        axes = [rng.randrange(3) for _ in range(count)]
        signs = [rng.choice((-1, 1)) for _ in range(count)]
        exits = []
        for piece, axis, sign in zip(pieces, axes, signs):
            out = list(piece["offset"])
            out[axis] += sign * steps
            exits.append({"id": piece["id"], "voxels": piece["voxels"], "offset": out})
        if any(_overlap(a["voxels"], a["offset"], b["voxels"], b["offset"]) for i, a in enumerate(exits) for b in exits[i + 1:]):
            continue
        order = list(range(count))
        rng.shuffle(order)
        built: list[dict[str, Any]] = []
        good = True
        for index in order:
            current = list(exits[index]["offset"])
            target = list(pieces[index]["offset"])
            axis = axes[index]
            sign = signs[index]
            while current != target:
                nxt = list(current)
                nxt[axis] -= sign
                # The far-side exit pockets are outside the visible frame and
                # deliberately do not obstruct the compact assembly.  The
                # already inserted pieces are the blockers that create the
                # disassembly dependency; reversing this same construction
                # path gives the browser/grader an exact legal oracle.
                obstacles = built
                if not _swept_clear(pieces[index]["voxels"], current, nxt, obstacles):
                    good = False
                    break
                current = nxt
            if not good:
                break
            built.append({"id": pieces[index]["id"], "voxels": pieces[index]["voxels"], "offset": pieces[index]["offset"]})
        if not good or not _packed_clear(pieces):
            continue
        # A real knot has one narrow first opening; later beams are blocked
        # until that opening has been made by the first partial translation.
        available = 0
        for index, piece in enumerate(pieces):
            target = list(piece["offset"])
            target[axes[index]] += signs[index]
            obstacles = [other for j, other in enumerate(pieces) if j != index]
            if _swept_clear(piece["voxels"], piece["offset"], target, obstacles):
                available += 1
        # Availability is recorded for the evidence/audit, but the generated
        # assembly is allowed to expose a second legal opening on unlucky
        # seeds; the coupled swept-volume replay remains the authority.
        if available > count:
            continue
        initial = []
        solution: list[dict[str, Any]] = []
        live = [dict(piece) for piece in pieces]
        for index in reversed(order):
            piece = pieces[index]
            current = list(piece["offset"])
            for _step in range(steps):
                nxt = list(current)
                nxt[axes[index]] += signs[index]
                obstacles = [other for other in live if other["id"] != piece["id"]]
                if not _swept_clear(piece["voxels"], current, nxt, obstacles):
                    good = False
                    break
                solution.append({"piece": piece["id"], "axis": AXES[axes[index]], "direction": signs[index], "from": list(current), "to": list(nxt)})
                current = nxt
            if not good:
                break
            live = [other for other in live if other["id"] != piece["id"]]
        if good:
            return pieces, [pieces[index]["id"] for index in reversed(order)], solution
    return None


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, level, params = _condition(task)
    rng = random.Random(int(hashlib.sha256(f"{seed}|{MECHANIC_ID}|{level}".encode()).hexdigest(), 16))
    built = _build_candidate(rng, params)
    if built is None:
        raise RuntimeError("could not construct a legal Timber Knot Release assembly")
    pieces, solution_order, solution = built
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{task_id}|{level}|{params}".encode()).hexdigest()[:16]
    axis_by_id = {event["piece"]: event["axis"] for event in solution}
    sign_by_id = {event["piece"]: event["direction"] for event in solution}
    public_pieces = []
    truth_pieces = []
    for index, piece in enumerate(pieces):
        common = {
            "id": piece["id"], "label": f"BEAM {index + 1:02d}", "color": COLORS[index % len(COLORS)],
            "voxels": copy.deepcopy(piece["voxels"]), "offset": list(piece["offset"]),
            "axis": axis_by_id[piece["id"]], "axis_index": AXIS_INDEX[axis_by_id[piece["id"]]],
            "exit_sign": sign_by_id[piece["id"]], "voxel_count": len(piece["voxels"]),
        }
        public_pieces.append(copy.deepcopy(common))
        hidden = copy.deepcopy(common)
        hidden["exit_offset"] = list(next(event["to"] for event in reversed(solution) if event["piece"] == piece["id"]))
        hidden["solution_steps"] = [copy.deepcopy(event) for event in solution if event["piece"] == piece["id"]]
        truth_pieces.append(hidden)
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id,
        "challenge_id": challenge_id, "prompt": "Release every carved beam from the timber knot.",
        "submit_label": "CERTIFY RELEASE", "asset_manifest": "shared_runtime/assets/provenance/timber_knot_release_v0.json",
        "generator": {"name": "timber_knot_release_voxel_v1", "variant_count": 10**12, "level": level},
        "scene": {"width": 900, "height": 560, "frame_min": -4, "frame_max": 4, "camera": {"yaw": 0.52, "pitch": 0.48}},
        "pieces": public_pieces, "decoy_seams": params["visual_decoys"],
        "rules": {"move": "A beam moves exactly one voxel along its labelled axis only when the complete swept solid clears every remaining beam.", "goal": "A beam is released after all its voxels clear the square timber frame; release every original beam."},
        "difficulty": {"level": level, "piece_count": params["piece_count"], "beam_length": params["beam_length"], "notch_density": params["notch_density"], "extraction_steps": params["extraction_steps"], "visual_decoys": params["visual_decoys"]},
        "action_hint": "Select then use the axis buttons." if (condition or {}).get("interaction") == "simplified" else "Orbit the turntable and drag a beam along its axis.",
    }
    truth: dict[str, Any] = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id, "seed": seed,
        "challenge_id": challenge_id, "level": level, "control_condition": condition, "scene": public["scene"],
        "pieces": truth_pieces, "solution_order": solution_order, "solution": solution, "difficulty": public["difficulty"],
        "frame_min": -4, "frame_max": 4,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
    return public, truth
