from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "branch_repair"
ANCHORS = ["XCOG-252", "XCOG-249", "XCOG-253"]


def _rng(seed: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).digest()[:8], "big"))


PROFILES: dict[int, dict[str, Any]] = {
    1: {"fiber_count": 2, "segments_per_fiber": 6, "missing_joins": 1, "false_joins": 1, "slice_count": 7, "crossing_density": 0.35},
    2: {"fiber_count": 3, "segments_per_fiber": 7, "missing_joins": 1, "false_joins": 1, "slice_count": 9, "crossing_density": 0.47},
    3: {"fiber_count": 3, "segments_per_fiber": 8, "missing_joins": 2, "false_joins": 1, "slice_count": 10, "crossing_density": 0.58},
    4: {"fiber_count": 4, "segments_per_fiber": 9, "missing_joins": 2, "false_joins": 2, "slice_count": 11, "crossing_density": 0.68},
    5: {"fiber_count": 5, "segments_per_fiber": 11, "missing_joins": 3, "false_joins": 3, "slice_count": 13, "crossing_density": 0.79},
}


def _round(value: float) -> float:
    value = round(float(value), 3)
    return 0.0 if value == 0 else value


def _edge(a: str, b: str) -> list[str]:
    return [a, b] if a < b else [b, a]


def _profile(task: dict[str, Any]) -> tuple[int, str, dict[str, Any] | None]:
    condition = copy.deepcopy(task.get("_control_condition"))
    if condition:
        level = int(condition["difficulty"])
        interaction = str(condition["interaction"])
        params = copy.deepcopy(condition.get("difficulty_parameters") or {})
        return level, interaction, params
    return 4, "full", copy.deepcopy(PROFILES[4])


def _point(fiber: int, index: int, count: int, rng: random.Random, density: float) -> list[float]:
    # The curves share a few depth bands but remain visibly separated in the
    # other two coordinates.  A crossing is a near-touch in 3D, not a painted
    # overlap: the public point cloud and all slice records use these values.
    t = index / max(1, count - 1)
    starts = [(-3.0, -1.85, -3.25), (-2.5, 1.55, -2.8), (2.75, -1.25, -2.7), (2.35, 1.65, -2.9), (0.0, 2.65, -3.0)]
    ends = [(2.85, 1.25, 3.2), (3.0, -1.55, 2.95), (-2.95, 1.4, 3.0), (-2.7, -1.7, 3.1), (2.9, 0.2, 3.0)]
    x0, y0, z0 = starts[fiber % len(starts)]
    x1, y1, z1 = ends[fiber % len(ends)]
    wave = math.sin(t * math.pi * (1.4 + fiber * 0.17) + fiber * 0.8)
    cross = math.sin(t * math.pi * (2.0 + density * 1.4) + fiber * 1.17)
    x = (1 - t) * x0 + t * x1 + 0.42 * wave + 0.12 * fiber * math.sin(t * math.pi) + 0.18 * density * cross
    y = (1 - t) * y0 + t * y1 + 0.52 * math.sin(t * math.pi * 1.55 + fiber) + 0.12 * density * math.cos(t * math.pi * 2.1 + fiber)
    z = (1 - t) * z0 + t * z1 + 0.23 * math.sin(t * math.pi * 2.3 + fiber) + 0.10 * density * cross
    jitter = (0.035 + fiber * 0.004) * (rng.random() - 0.5)
    return [_round(x + jitter), _round(y + jitter * 0.7), _round(z - jitter)]


def _slice_records(nodes: list[dict[str, Any]], focus: list[int], slice_count: int, view: str) -> list[dict[str, Any]]:
    axes = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}[view]
    level = -4.0 + 8.0 * int(focus[axes[2]]) / max(1, slice_count - 1)
    records: list[dict[str, Any]] = []
    for node in nodes:
        point = node["p"]
        if abs(float(point[axes[2]]) - level) <= 0.72:
            records.append({"id": node["id"], "u": _round(point[axes[0]]), "v": _round(point[axes[1]])})
    return sorted(records, key=lambda item: item["id"])


def _slice_digest(records: list[dict[str, Any]]) -> str:
    return "|".join(f"{item['id']}:{float(item['u']):.3f}:{float(item['v']):.3f}" for item in records)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    level, interaction, params = _profile(task)
    defaults = PROFILES[level]
    for key, value in defaults.items():
        params.setdefault(key, value)
    fiber_count = int(params["fiber_count"])
    segments = int(params["segments_per_fiber"])
    slice_count = int(params["slice_count"])
    missing_count = int(params["missing_joins"])
    false_count = int(params["false_joins"])
    rng = _rng(seed)
    palette = rng.choice([
        {"target": "#ffcf58", "fibre": ["#61d6ff", "#cb8cff", "#ff8aa5", "#77e39c"], "glass": "#102331"},
        {"target": "#ff9e63", "fibre": ["#78e3ff", "#d59aff", "#f4e56b", "#72e3b0"], "glass": "#151d32"},
        {"target": "#f8e16c", "fibre": ["#7bd6ff", "#e28cff", "#ff91c8", "#9ce47b"], "glass": "#1e2135"},
    ])
    target_labels = ("VIOLET THREAD", "COBALT THREAD", "AMBER THREAD", "ROSE THREAD", "MINT THREAD")
    target_label = target_labels[rng.randrange(len(target_labels))]
    nodes: list[dict[str, Any]] = []
    fiber_nodes: list[list[str]] = []
    used_labels: set[str] = set()
    for fiber in range(fiber_count):
        ids: list[str] = []
        for index in range(segments):
            # The public identifier is an opaque stable token.  It does not
            # encode fibre membership or position in a fibre.
            node_id = "node-" + hashlib.sha256(f"{seed}|{fiber}|{index}".encode()).hexdigest()[:10]
            label = f"S{rng.randrange(100, 1000):03d}"
            while label in used_labels:
                label = f"S{rng.randrange(100, 1000):03d}"
            used_labels.add(label)
            ids.append(node_id)
            nodes.append({"id": node_id, "p": _point(fiber, index, segments, rng, float(params["crossing_density"])), "label": label})
        fiber_nodes.append(ids)

    # Move selected decoy nodes to the target fibre's neighbourhood so that
    # each orthogonal slice can be misleading while the 3D depth separates it.
    target_fiber = rng.randrange(fiber_count)
    target_ids = fiber_nodes[target_fiber]
    other_fibers = [fiber for fiber in range(fiber_count) if fiber != target_fiber]
    node_by_id = {item["id"]: item for item in nodes}
    candidate_indices = list(range(1, segments - 1))
    rng.shuffle(candidate_indices)
    missing_indices = sorted(candidate_indices[:missing_count])
    crossing_pool = [index for index in candidate_indices if index not in missing_indices]
    crossing_indices = sorted(crossing_pool[:false_count])
    for count, index in enumerate(crossing_indices):
        decoy_fiber = other_fibers[count % len(other_fibers)]
        target = node_by_id[target_ids[index]]["p"]
        offset = (0.28 + 0.13 * rng.random(), 0.20 + 0.16 * rng.random(), 0.10 + 0.12 * rng.random())
        node_by_id[fiber_nodes[decoy_fiber][index]]["p"] = [_round(target[0] + offset[0]), _round(target[1] + offset[1]), _round(target[2] + offset[2])]

    true_edges: list[list[str]] = []
    for ids in fiber_nodes:
        true_edges.extend(_edge(ids[i], ids[i + 1]) for i in range(len(ids) - 1))
    missing_edges = [_edge(target_ids[index], target_ids[index + 1]) for index in missing_indices]
    false_edges = [_edge(target_ids[index], fiber_nodes[other_fibers[i % len(other_fibers)]][index]) for i, index in enumerate(crossing_indices)]
    missing_set = {tuple(item) for item in missing_edges}
    initial_edges = [edge for edge in true_edges if tuple(edge) not in missing_set] + false_edges
    initial_edges = sorted(initial_edges)
    true_edges = sorted(true_edges)
    focus = [slice_count // 2, slice_count // 2, slice_count // 2]
    views = {
        "xy": {"axes": ["x", "y"], "normal": "z", "width": 230, "height": 154, "scale": 24},
        "xz": {"axes": ["x", "z"], "normal": "y", "width": 230, "height": 154, "scale": 24},
        "yz": {"axes": ["y", "z"], "normal": "x", "width": 230, "height": 154, "scale": 24},
    }
    slice_contract = {
        "minimum": -4.0,
        "maximum": 4.0,
        "step": _round(8.0 / max(1, slice_count - 1)),
        "thickness": 0.72,
        "index_count": slice_count,
        "focus_order": ["x", "y", "z"],
    }
    requirements = {
        "repair_count": missing_count + false_count,
        "max_events": int(60 + fiber_count * segments * 2),
    }
    task_id = str(task.get("id") or "branch_repair_seed_0001@0.1")
    condition_token = f"|difficulty={level}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Repair the marked fibre without absorbing its neighbours.",
        "submit_label": "CERTIFY REPAIRED BRANCH",
        "target_label": target_label,
        "seed_segment_id": target_ids[0],
        "nodes": nodes,
        "initial_edges": initial_edges,
        "views": views,
        "focus": focus,
        "slice_contract": slice_contract,
        "requirements": requirements,
        "palette": palette,
        "generator": {"name": "opaque_seeded_fibre_topology_bridge_v2", "source_anchors": ANCHORS},
        "asset_manifest": "shared_runtime/assets/provenance/branch_repair_v0.json",
        "render_boundary": "The browser receives opaque segment geometry and visible edit affordances for an ordinary UI solve; target topology and construction truth remain server-side grading data.",
        "interaction": interaction,
    }
    truth: dict[str, Any] = {
        **copy.deepcopy(public),
        "seed": seed,
        "level": level,
        "interaction": interaction,
        "true_edges": true_edges,
        "missing_edges": missing_edges,
        "false_edges": false_edges,
        "target_nodes": target_ids,
        "node_fiber": {node_id: fiber for fiber, ids in enumerate(fiber_nodes) for node_id in ids},
        "initial_edges": initial_edges,
    }
    public.pop("seed", None)
    if task.get("_control_condition"):
        public["control_condition"] = copy.deepcopy(task["_control_condition"])
        truth["control_condition"] = copy.deepcopy(task["_control_condition"])
    # Public state gets the records for the initial linked planes, but never
    # the hidden joins or the complete target component.
    public["initial_slice_records"] = {view: _slice_records(nodes, focus, slice_count, view) for view in views}
    return public, truth


def slice_records(public_state: dict[str, Any], focus: list[int], view: str) -> list[dict[str, Any]]:
    return _slice_records(list(public_state.get("nodes") or []), focus, int((public_state.get("slice_contract") or {}).get("index_count", 1)), view)


def slice_digest(records: list[dict[str, Any]]) -> str:
    return _slice_digest(records)
