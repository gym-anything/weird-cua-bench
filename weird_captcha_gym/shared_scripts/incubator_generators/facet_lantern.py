"""Deterministic original 3D vertex-connection worlds for Facet Lantern."""

from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "facet_lantern"
DEFAULT_PARAMETERS: dict[str, Any] = {
    "shape": "bipyramid",
    "ring_vertices": 6,
    "polygon_count": 3,
    "target_stride": 2,
    "initial_connections": 3,
    "initial_yaw": 30,
    "occlusion_band": 0.25,
    "rotation_step_degrees": 15,
}
PARAMETER_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode()).digest()[:8], "big")


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    raw = task.get("_control_condition")
    if raw is None:
        raw = (task.get("metadata") or {}).get("control_condition")
    if raw is None:
        return None, copy.deepcopy(DEFAULT_PARAMETERS)
    if not isinstance(raw, dict):
        raise ValueError("facet lantern control condition is malformed")
    values = copy.deepcopy(raw.get("difficulty_parameters") or {})
    if set(values) != PARAMETER_FIELDS:
        raise ValueError("facet lantern difficulty profile fields do not match generator contract")
    if values["shape"] != "bipyramid":
        raise ValueError("facet lantern shape must be bipyramid")
    if not isinstance(values["ring_vertices"], int) or not 4 <= values["ring_vertices"] <= 10:
        raise ValueError("facet lantern ring_vertices must be 4 through 10")
    if not isinstance(values["polygon_count"], int) or not 2 <= values["polygon_count"] <= 5:
        raise ValueError("facet lantern polygon_count must be 2 through 5")
    if not isinstance(values["target_stride"], int) or not 1 <= values["target_stride"] <= 5:
        raise ValueError("facet lantern target_stride is outside the supported range")
    if not isinstance(values["initial_connections"], int) or not 0 <= values["initial_connections"] <= 12:
        raise ValueError("facet lantern initial_connections is outside the supported range")
    if not isinstance(values["initial_yaw"], (int, float)):
        raise ValueError("facet lantern initial_yaw must be numeric")
    if not 0 <= float(values["initial_yaw"]) < 360:
        raise ValueError("facet lantern initial_yaw must be in [0, 360)")
    if not isinstance(values["occlusion_band"], (int, float)) or not 0.05 <= float(values["occlusion_band"]) <= 0.5:
        raise ValueError("facet lantern occlusion_band is outside the supported range")
    if not isinstance(values["rotation_step_degrees"], (int, float)) or not 5 <= float(values["rotation_step_degrees"]) <= 45:
        raise ValueError("facet lantern rotation_step_degrees is outside the supported range")
    return copy.deepcopy(raw), values


def _edge(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((str(a), str(b))))


def _world(parameters: dict[str, Any], seed: str) -> tuple[dict[str, Any], list[list[str]], list[dict[str, Any]]]:
    ring_count = int(parameters["ring_vertices"])
    vertices: list[dict[str, Any]] = [
        {"id": "v0", "label": "A", "x": 0.0, "y": 1.38, "z": 0.0},
    ]
    for index in range(ring_count):
        angle = (2 * math.pi * index) / ring_count
        vertices.append({
            "id": f"v{index + 1}",
            "label": chr(65 + index + 1),
            "x": round(math.cos(angle), 5),
            "y": 0.0,
            "z": round(math.sin(angle), 5),
        })
    bottom_id = ring_count + 1
    vertices.append({"id": f"v{bottom_id}", "label": chr(65 + bottom_id), "x": 0.0, "y": -1.38, "z": 0.0})

    faces: list[list[str]] = []
    for index in range(ring_count):
        left = f"v{index + 1}"
        right = f"v{(index + 1) % ring_count + 1}"
        faces.append(["v0", left, right])
    for index in range(ring_count):
        left = f"v{index + 1}"
        right = f"v{(index + 1) % ring_count + 1}"
        faces.append([f"v{bottom_id}", right, left])

    face_count = len(faces)
    stride = int(parameters["target_stride"])
    target_indices: list[int] = []
    cursor = 0
    while len(target_indices) < int(parameters["polygon_count"]):
        candidate = (cursor * stride) % face_count
        if candidate not in target_indices:
            target_indices.append(candidate)
        cursor += 1
    targets = [
        {"id": f"facet-{index + 1}", "vertices": faces[face_index], "face_index": face_index}
        for index, face_index in enumerate(target_indices)
    ]
    required = sorted({_edge(a, b) for target in targets for a, b in zip(target["vertices"], target["vertices"][1:] + target["vertices"][:1])})
    rng = random.Random(_seed_int(seed, "facet-lantern-initial-edges"))
    shuffled = list(required)
    rng.shuffle(shuffled)
    initial = sorted(shuffled[: min(int(parameters["initial_connections"]), max(0, len(shuffled) - 1))])
    world = {
        "canvas": {"width": 920, "height": 560},
        "vertices": vertices,
        "faces": faces,
        "targets": targets,
        "connections": [list(edge) for edge in initial],
        "initial_yaw": float(parameters["initial_yaw"]),
        "occlusion_band": float(parameters["occlusion_band"]),
        "rotation_step_degrees": float(parameters["rotation_step_degrees"]),
        "shape": parameters["shape"],
    }
    return world, [list(edge) for edge in required], targets


def _score(connections: list[list[str]], targets: list[dict[str, Any]], vertices: list[dict[str, Any]]) -> tuple[int, int, int]:
    edges = {_edge(edge[0], edge[1]) for edge in connections}
    complete = 0
    polygon_points = 0
    for target in targets:
        needed = {
            _edge(a, b)
            for a, b in zip(target["vertices"], target["vertices"][1:] + target["vertices"][:1])
        }
        if needed <= edges:
            complete += 1
            polygon_points += 10 * len(target["vertices"])
    degree = {str(vertex["id"]): 0 for vertex in vertices}
    for first, second in edges:
        degree[first] += 1
        degree[second] += 1
    isolated = sum(value == 0 for value in degree.values())
    return 10 * len(edges) + polygon_points - isolated, complete, isolated


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _condition(task)
    world, required, targets = _world(parameters, seed)
    vertices = world["vertices"]
    target_score, complete, isolated = _score(world["connections"], targets, vertices)
    solved_score, _, solved_isolated = _score([list(edge) for edge in required], targets, vertices)
    challenge_id = hashlib.sha256(f"{seed}|facet-lantern|{json_stable(parameters)}".encode()).hexdigest()[:12]
    interaction = str((condition or {}).get("interaction") or "full")
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Rotate the lantern and close every requested facet.",
        "submit_label": "CERTIFY LANTERN",
        "asset_manifest": "shared_runtime/assets/provenance/facet_lantern_v0.json",
        "generator": {"name": "facet_lantern_bipyramid_v1", "variant_count": 10_000_000},
        "interaction": interaction,
        "control_condition": copy.deepcopy(condition) if condition is not None else {"interaction": "full"},
        "world": copy.deepcopy(world),
        "targets": copy.deepcopy(targets),
        "required_connection_count": len(required),
        "target_score": solved_score,
        "score": target_score,
        "completed_facets": complete,
        "isolated_vertices": isolated,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition) if condition is not None else {"interaction": "full"},
        "world": copy.deepcopy(world),
        "targets": copy.deepcopy(targets),
        "required_connections": copy.deepcopy(required),
        "target_score": solved_score,
        "initial_score": target_score,
        "initial_completed_facets": complete,
        "initial_isolated_vertices": isolated,
        "solved_isolated_vertices": solved_isolated,
    }
    return public, truth


def json_stable(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
