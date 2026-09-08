"""Seeded planar graph construction for Knotless Starmap.

The visible challenge is a straight-line drawing of a fixed planar graph.  A
seed chooses the graph family and an initial permutation of the same visible
vertex slots; the browser may move vertices, but it never receives the
canonical layout used by the scripted implementation witness.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import random
from typing import Any


MECHANIC_ID = "knotless_starmap"
CANVAS = {"width": 860, "height": 500}

DEFAULT_PARAMETERS: dict[str, Any] = {
    "topology": "wheel",
    "ring_vertices": 8,
    "scramble_rounds": 3,
    "minimum_crossings": 8,
    "minimum_vertex_separation": 28,
}
PARAMETER_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8],
        "big",
    )


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    raw = task.get("_control_condition")
    if raw is None:
        raw = (task.get("metadata") or {}).get("control_condition")
    if raw is None:
        return None, copy.deepcopy(DEFAULT_PARAMETERS)
    if not isinstance(raw, dict):
        raise ValueError("starmap control condition is malformed")
    supplied = dict(raw.get("difficulty_parameters") or {})
    if set(supplied) != PARAMETER_FIELDS:
        raise ValueError("starmap difficulty profile fields do not match the generator contract")
    values = copy.deepcopy(supplied)
    topology = values.get("topology")
    if topology not in {"cycle", "wheel", "double_ring"}:
        raise ValueError("starmap topology is unsupported")
    ring_vertices = values.get("ring_vertices")
    if isinstance(ring_vertices, bool) or not isinstance(ring_vertices, int) or not 4 <= ring_vertices <= 8:
        raise ValueError("starmap ring_vertices must be an integer from 4 through 8")
    rounds = values.get("scramble_rounds")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 6:
        raise ValueError("starmap scramble_rounds must be an integer from 1 through 6")
    crossings = values.get("minimum_crossings")
    if isinstance(crossings, bool) or not isinstance(crossings, int) or not 0 <= crossings <= 40:
        raise ValueError("starmap minimum_crossings is outside the supported range")
    separation = values.get("minimum_vertex_separation")
    if isinstance(separation, bool) or not isinstance(separation, int) or not 20 <= separation <= 40:
        raise ValueError("starmap minimum_vertex_separation is outside the supported range")
    if topology == "cycle" and ring_vertices < 4:
        raise ValueError("starmap cycle is too small")
    return copy.deepcopy(raw), values


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-7 <= p[0] <= max(a[0], b[0]) + 1e-7
        and min(a[1], b[1]) - 1e-7 <= p[1] <= max(a[1], b[1]) + 1e-7
        and abs(_orient(a, b, p)) <= 1e-7
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    ab_c, ab_d = _orient(a, b, c), _orient(a, b, d)
    cd_a, cd_b = _orient(c, d, a), _orient(c, d, b)
    if ((ab_c > 1e-7 and ab_d < -1e-7) or (ab_c < -1e-7 and ab_d > 1e-7)) and ((cd_a > 1e-7 and cd_b < -1e-7) or (cd_a < -1e-7 and cd_b > 1e-7)):
        return True
    return (
        _on_segment(a, b, c)
        or _on_segment(a, b, d)
        or _on_segment(c, d, a)
        or _on_segment(c, d, b)
    )


def crossing_pairs(edges: list[list[str]], positions: dict[str, tuple[float, float]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for first, second in itertools.combinations(range(len(edges)), 2):
        edge_a, edge_b = edges[first], edges[second]
        if set(edge_a) & set(edge_b):
            continue
        a, b = (positions[edge_a[0]], positions[edge_a[1]])
        c, d = (positions[edge_b[0]], positions[edge_b[1]])
        if _segments_intersect(a, b, c, d):
            result.append((first, second))
    return result


def _point(x: float, y: float) -> list[float]:
    return [round(float(x), 2), round(float(y), 2)]


def _canonical_layout(parameters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[str]]]:
    count = int(parameters["ring_vertices"])
    topology = str(parameters["topology"])
    center_x, center_y = 430.0, 250.0
    vertices: list[dict[str, Any]] = []
    edges: list[list[str]] = []

    def add_vertex(vertex_id: str, x: float, y: float, role: str) -> None:
        vertices.append({"id": vertex_id, "label": vertex_id[1:].upper(), "x": round(x, 2), "y": round(y, 2), "role": role})

    outer_radius_x, outer_radius_y = 310.0, 160.0
    for index in range(count):
        angle = -math.pi / 2 + math.tau * index / count
        add_vertex(
            f"v{index}",
            center_x + outer_radius_x * math.cos(angle),
            center_y + outer_radius_y * math.sin(angle),
            "outer",
        )
    for index in range(count):
        edges.append([f"v{index}", f"v{(index + 1) % count}"])

    if topology == "wheel":
        add_vertex("v" + str(count), center_x, center_y, "hub")
        for index in range(count):
            edges.append([f"v{count}", f"v{index}"])
    elif topology == "double_ring":
        inner_offset = count
        inner_radius_x, inner_radius_y = 150.0, 86.0
        for index in range(count):
            angle = -math.pi / 2 + math.tau * index / count
            add_vertex(
                f"v{inner_offset + index}",
                center_x + inner_radius_x * math.cos(angle),
                center_y + inner_radius_y * math.sin(angle),
                "inner",
            )
        for index in range(count):
            edges.append([f"v{inner_offset + index}", f"v{inner_offset + (index + 1) % count}"])
            edges.append([f"v{index}", f"v{inner_offset + index}"])
            edges.append([f"v{inner_offset + index}", f"v{(index + 1) % count}"])
        hub_id = f"v{2 * count}"
        add_vertex(hub_id, center_x, center_y, "hub")
        for index in range(count):
            edges.append([hub_id, f"v{inner_offset + index}"])

    return vertices, edges


def _initial_positions(
    seed: str,
    vertices: list[dict[str, Any]],
    edges: list[list[str]],
    parameters: dict[str, Any],
) -> tuple[dict[str, list[float]], int]:
    rng = random.Random(_seed_int(seed, "initial-scramble"))
    canonical = {item["id"]: (float(item["x"]), float(item["y"])) for item in vertices}
    ids = [item["id"] for item in vertices]
    minimum = int(parameters["minimum_crossings"])
    rounds = int(parameters["scramble_rounds"])
    chosen: dict[str, list[float]] | None = None
    chosen_count = -1
    for _attempt in range(800):
        permutation = list(range(len(ids)))
        for _ in range(rounds):
            first, second = rng.sample(range(len(ids)), 2)
            permutation[first], permutation[second] = permutation[second], permutation[first]
        current = {
            vertex_id: [round(canonical[ids[permutation[index]]][0], 2), round(canonical[ids[permutation[index]]][1], 2)]
            for index, vertex_id in enumerate(ids)
        }
        positions = {key: (value[0], value[1]) for key, value in current.items()}
        count = len(crossing_pairs(edges, positions))
        if count > chosen_count:
            chosen, chosen_count = current, count
        if count >= minimum and any(current[key] != _point(*canonical[key]) for key in ids):
            return current, count
    if chosen is None:
        raise ValueError("could not scramble starmap")
    if chosen_count < minimum:
        raise ValueError(f"could not generate a starmap with {minimum} crossings")
    return chosen, chosen_count


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _condition(task)
    vertices, edges = _canonical_layout(parameters)
    initial_positions, initial_crossings = _initial_positions(seed, vertices, edges, parameters)
    canonical_positions = {item["id"]: _point(item["x"], item["y"]) for item in vertices}
    visible_vertices = []
    for item in vertices:
        visible = copy.deepcopy(item)
        visible["x"], visible["y"] = initial_positions[item["id"]]
        visible_vertices.append(visible)
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    parameter_token = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{parameter_token}".encode("utf-8")).hexdigest()[:16]
    world = {
        "canvas": copy.deepcopy(CANVAS),
        "vertices": visible_vertices,
        "edges": copy.deepcopy(edges),
        "minimum_vertex_separation": int(parameters["minimum_vertex_separation"]),
        "initial_crossings": initial_crossings,
        "palette_seed": _seed_int(seed, "palette") % 1000,
    }
    common = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Untangle the star map until no luminous edges cross.",
        "submit_label": "CERTIFY MAP",
        "world": world,
        "generator": {
            "name": "knotless_planar_embedding_v0",
            "seeded": True,
            "variant_count": 10**12,
        },
        "asset_manifest": "shared_runtime/assets/provenance/knotless_starmap_v0.json",
    }
    public_state = copy.deepcopy(common)
    ground_truth = copy.deepcopy(common)
    ground_truth.update({
        "seed": seed,
        "parameters": copy.deepcopy(parameters),
        "solution_positions": canonical_positions,
    })
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth

