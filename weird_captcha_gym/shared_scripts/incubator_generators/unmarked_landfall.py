from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import deque
from typing import Any


MECHANIC_ID = "unmarked_landfall"
GENERATOR_NAME = "fictional_field_atlas_v1"
VARIANT_COUNT = 9_700_000_000
MAP_WIDTH = 720
MAP_HEIGHT = 480
PANORAMA_WIDTH = 960
PANORAMA_HEIGHT = 540

FEATURES = (
    "script",
    "milestone",
    "pole",
    "roof",
    "crop",
    "plate",
)

FEATURE_LABELS = {
    "script": "SIGN SCRIPT",
    "milestone": "MILESTONE POST",
    "pole": "POLE BANDING",
    "roof": "ROOF PITCH",
    "crop": "FIELD CROP",
    "plate": "PLATE SCHEME",
}

FEATURE_VALUES = {
    feature: [f"{feature}-{index}" for index in range(4)] for feature in FEATURES
}

DEFAULT_PARAMETERS = {
    "province_count": 12,
    "feature_count": 6,
    "ambiguity_depth": 4,
    "road_node_count": 7,
    "step_budget": 8,
    "guide_page_size": 3,
    "pin_radius": 16,
    "map_max_zoom": 2.8,
}

NAME_STARTS = (
    "Alder",
    "Brindle",
    "Cairn",
    "Dovra",
    "Esker",
    "Fallow",
    "Gannet",
    "Hearth",
    "Ivory",
    "Juniper",
    "Kestrel",
    "Lumen",
    "Morrow",
    "Nacre",
    "Orison",
    "Plover",
    "Quill",
    "Rill",
    "Sable",
    "Tern",
)

NAME_ENDS = (
    " Reach",
    " Vale",
    " March",
    " Fen",
    " Coast",
    " Fold",
    " Weald",
    " Rise",
    " Sound",
    " Ward",
)

BASE_NODES = (
    (0.50, 0.52),
    (0.31, 0.43),
    (0.69, 0.43),
    (0.18, 0.24),
    (0.22, 0.76),
    (0.82, 0.24),
    (0.78, 0.76),
    (0.08, 0.10),
    (0.92, 0.90),
)

BASE_EDGES = (
    (0, 1),
    (0, 2),
    (1, 3),
    (1, 4),
    (2, 5),
    (2, 6),
    (3, 7),
    (6, 8),
)

LANDMARK_KINDS = ("wind-pump", "stone-ring", "signal-pine", "reed-well")


def _seed_int(seed: str, parameters: dict[str, Any]) -> int:
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|atlas-v1|{encoded}".encode("utf-8")
    ).hexdigest()
    return int(digest[:16], 16)


def _normalise_parameters(raw: dict[str, Any]) -> dict[str, Any]:
    values = dict(DEFAULT_PARAMETERS)
    values.update(raw)
    values = {
        "province_count": int(values["province_count"]),
        "feature_count": int(values["feature_count"]),
        "ambiguity_depth": int(values["ambiguity_depth"]),
        "road_node_count": int(values["road_node_count"]),
        "step_budget": int(values["step_budget"]),
        "guide_page_size": int(values["guide_page_size"]),
        "pin_radius": float(values["pin_radius"]),
        "map_max_zoom": float(values["map_max_zoom"]),
    }
    if not 4 <= values["province_count"] <= 16:
        raise ValueError("province_count must be between 4 and 16")
    if not 3 <= values["feature_count"] <= len(FEATURES):
        raise ValueError("feature_count must be between 3 and 6")
    if not 2 <= values["ambiguity_depth"] <= values["feature_count"]:
        raise ValueError("ambiguity_depth must fit the active evidence classes")
    if values["province_count"] < values["ambiguity_depth"] + 1:
        raise ValueError("province_count is too small for the ambiguity contract")
    if not 4 <= values["road_node_count"] <= len(BASE_NODES):
        raise ValueError("road_node_count must be between 4 and 9")
    if values["road_node_count"] < values["feature_count"]:
        raise ValueError("each active evidence class needs a reachable road node")
    if not 3 <= values["step_budget"] <= 14:
        raise ValueError("step_budget is outside the supported range")
    if not 2 <= values["guide_page_size"] <= 4:
        raise ValueError("guide_page_size must be between 2 and 4")
    if not 8 <= values["pin_radius"] <= 34:
        raise ValueError("pin_radius is outside the supported range")
    if not 2.0 <= values["map_max_zoom"] <= 3.5:
        raise ValueError("map_max_zoom is outside the supported range")
    return values


def _edges(node_count: int) -> list[tuple[int, int]]:
    return [edge for edge in BASE_EDGES if max(edge) < node_count]


def _adjacency(node_count: int) -> dict[int, list[int]]:
    result = {index: [] for index in range(node_count)}
    for left, right in _edges(node_count):
        result[left].append(right)
        result[right].append(left)
    for values in result.values():
        values.sort()
    return result


def _shortest_cover_walk(node_count: int, start: int) -> list[int]:
    adjacency = _adjacency(node_count)
    full_mask = (1 << node_count) - 1
    queue: deque[tuple[int, int]] = deque([(start, 1 << start)])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {
        (start, 1 << start): None
    }
    end: tuple[int, int] | None = None
    while queue:
        state = queue.popleft()
        node, mask = state
        if mask == full_mask:
            end = state
            break
        for neighbour in adjacency[node]:
            next_state = (neighbour, mask | (1 << neighbour))
            if next_state not in previous:
                previous[next_state] = state
                queue.append(next_state)
    if end is None:
        raise ValueError("road graph is disconnected")
    walk: list[int] = []
    cursor: tuple[int, int] | None = end
    while cursor is not None:
        walk.append(cursor[0])
        cursor = previous[cursor]
    return list(reversed(walk))


def _transform_point(point: tuple[float, float], transform: int) -> tuple[float, float]:
    x, y = point
    if transform == 1:
        return 1.0 - x, y
    if transform == 2:
        return x, 1.0 - y
    if transform == 3:
        return 1.0 - x, 1.0 - y
    return x, y


def _bearing(source: dict[str, float], target: dict[str, float]) -> float:
    dx = float(target["x"]) - float(source["x"])
    dy = float(target["y"]) - float(source["y"])
    return round((math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0, 2)


def _angle_separation(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _clear_bearing(
    rng: random.Random,
    occupied: list[float],
    minimum_separation: float,
) -> float:
    viable = [
        float(candidate)
        for candidate in range(0, 360, 5)
        if all(
            _angle_separation(float(candidate), other) >= minimum_separation
            for other in occupied
        )
    ]
    if not viable:
        raise ValueError("road geometry leaves no unobstructed evidence bearing")
    return rng.choice(viable)


def _region_layout(count: int) -> tuple[int, int, float, float]:
    if count <= 4:
        columns = 2
    elif count <= 6:
        columns = 3
    else:
        columns = 4
    rows = math.ceil(count / columns)
    margin_x, margin_y = 22.0, 20.0
    width = (MAP_WIDTH - margin_x * 2) / columns
    height = (MAP_HEIGHT - margin_y * 2) / rows
    return columns, rows, width, height


def _make_region(
    rng: random.Random,
    *,
    index: int,
    count: int,
    name: str,
    province_id: str,
    signature: dict[str, str],
    node_count: int,
) -> dict[str, Any]:
    columns, _rows, cell_width, cell_height = _region_layout(count)
    column, row = index % columns, index // columns
    x = 22.0 + column * cell_width
    y = 20.0 + row * cell_height
    inset = 5.0
    left, top = x + inset, y + inset
    width, height = cell_width - inset * 2, cell_height - inset * 2
    jitter = min(8.0, width * 0.04, height * 0.06)
    polygon = [
        [round(left + rng.uniform(0, jitter), 2), round(top + rng.uniform(0, jitter), 2)],
        [round(left + width - rng.uniform(0, jitter), 2), round(top + rng.uniform(0, jitter), 2)],
        [round(left + width - rng.uniform(0, jitter), 2), round(top + height - rng.uniform(0, jitter), 2)],
        [round(left + rng.uniform(0, jitter), 2), round(top + height - rng.uniform(0, jitter), 2)],
    ]
    transform = rng.randrange(4)
    nodes: list[dict[str, Any]] = []
    for node_index, base in enumerate(BASE_NODES[:node_count]):
        nx, ny = _transform_point(base, transform)
        nodes.append(
            {
                "id": f"road-{node_index}",
                "x": round(left + (0.08 + nx * 0.84) * width, 2),
                "y": round(top + (0.08 + ny * 0.84) * height, 2),
            }
        )
    edges = [[f"road-{a}", f"road-{b}"] for a, b in _edges(node_count)]
    adjacency = _adjacency(node_count)
    leaves = [index for index, neighbours in adjacency.items() if len(neighbours) == 1]
    landmark_index = rng.choice(leaves)
    return {
        "id": province_id,
        "name": name,
        "signature": copy.deepcopy(signature),
        "polygon": polygon,
        "label": [round(left + width * 0.5, 2), round(top + 14, 2)],
        "bounds": {
            "x": round(left, 2),
            "y": round(top, 2),
            "width": round(width, 2),
            "height": round(height, 2),
        },
        "road": {
            "nodes": nodes,
            "edges": edges,
            "landmark_node": f"road-{landmark_index}",
            "landmark_kind": rng.choice(LANDMARK_KINDS),
        },
        "wash": rng.randrange(5),
    }


def _province_signatures(
    rng: random.Random,
    province_count: int,
    active_features: list[str],
    ambiguity_depth: int,
) -> tuple[list[dict[str, str]], list[str]]:
    target = {feature: rng.choice(FEATURE_VALUES[feature]) for feature in active_features}
    critical = rng.sample(active_features, ambiguity_depth)
    signatures = [target]
    for feature in critical:
        decoy = dict(target)
        alternatives = [value for value in FEATURE_VALUES[feature] if value != target[feature]]
        decoy[feature] = rng.choice(alternatives)
        signatures.append(decoy)
    seen = {tuple(signature[feature] for feature in active_features) for signature in signatures}
    while len(signatures) < province_count:
        candidate = {feature: rng.choice(FEATURE_VALUES[feature]) for feature in active_features}
        token = tuple(candidate[feature] for feature in active_features)
        if token in seen:
            continue
        seen.add(token)
        signatures.append(candidate)
    return signatures, critical


def _world_fingerprint(public_contract: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(public_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    raw_parameters = dict((condition or {}).get("difficulty_parameters") or {})
    parameters = _normalise_parameters(raw_parameters)
    rng = random.Random(_seed_int(seed, parameters))
    task_id = str(task.get("id") or "unmarked_landfall_seed_0001@0.1")
    interaction = str((condition or {}).get("interaction") or "full")
    active_features = list(FEATURES[: parameters["feature_count"]])

    signatures, critical_features = _province_signatures(
        rng,
        parameters["province_count"],
        active_features,
        parameters["ambiguity_depth"],
    )
    names = [f"{start}{end}" for start in NAME_STARTS for end in NAME_ENDS]
    rng.shuffle(names)
    target_signature = signatures[0]
    records = []
    for index, signature in enumerate(signatures):
        province_id = f"province-{hashlib.sha256(f'{seed}|province|{index}'.encode()).hexdigest()[:8]}"
        records.append(
            {
                "id": province_id,
                "name": names[index],
                "signature": signature,
                "is_target": index == 0,
            }
        )
    rng.shuffle(records)
    regions = [
        _make_region(
            rng,
            index=index,
            count=len(records),
            name=record["name"],
            province_id=record["id"],
            signature=record["signature"],
            node_count=parameters["road_node_count"],
        )
        for index, record in enumerate(records)
    ]
    target_region = next(region for region in regions if region["signature"] == target_signature)
    target_id = target_region["id"]

    adjacency = _adjacency(parameters["road_node_count"])
    leaves = [index for index, neighbours in adjacency.items() if len(neighbours) == 1]
    landmark_index = int(target_region["road"]["landmark_node"].split("-")[-1])
    landing_candidates = [index for index in leaves if index != landmark_index]
    landing_index = rng.choice(landing_candidates or leaves)
    solution_walk = _shortest_cover_walk(parameters["road_node_count"], landing_index)
    if len(solution_walk) - 1 > parameters["step_budget"]:
        raise ValueError("step budget cannot cover the generated road graph")
    unique_walk: list[int] = []
    for node_index in solution_walk:
        if node_index not in unique_walk:
            unique_walk.append(node_index)
    feature_order = critical_features + [
        feature for feature in active_features if feature not in critical_features
    ]
    clue_node_by_feature = {
        feature: unique_walk[index] for index, feature in enumerate(feature_order)
    }
    map_nodes = {
        int(node["id"].split("-")[-1]): node for node in target_region["road"]["nodes"]
    }
    journey_nodes: list[dict[str, Any]] = []
    for node_index in range(parameters["road_node_count"]):
        roads = []
        for neighbour in adjacency[node_index]:
            roads.append(
                {
                    "to": f"road-{neighbour}",
                    "bearing": _bearing(map_nodes[node_index], map_nodes[neighbour]),
                }
            )
        landmark = None
        occupied_bearings = [float(road["bearing"]) for road in roads]
        if node_index == landmark_index:
            landmark = {
                "kind": target_region["road"]["landmark_kind"],
                "bearing": _clear_bearing(rng, occupied_bearings, 24.0),
            }
            occupied_bearings.append(float(landmark["bearing"]))
        clue = None
        for feature, clue_node in clue_node_by_feature.items():
            if clue_node == node_index:
                clue = {
                    "feature": feature,
                    "value": target_signature[feature],
                    "bearing": _clear_bearing(rng, occupied_bearings, 30.0),
                }
                break
        journey_nodes.append(
            {
                "id": f"road-{node_index}",
                "roads": roads,
                "clue": clue,
                "landmark": landmark,
                "scene_variant": rng.randrange(8),
            }
        )

    landing_node = f"road-{landing_index}"
    landing_map_node = map_nodes[landing_index]
    initial_yaw = float(rng.randrange(0, 12) * 30)
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|{json.dumps(parameters, sort_keys=True)}".encode("utf-8")
    ).hexdigest()[:14]
    guide_provinces = [
        {
            "id": region["id"],
            "name": region["name"],
            "signature": copy.deepcopy(region["signature"]),
        }
        for region in regions
    ]
    public_contract = {
        "active_features": active_features,
        "feature_labels": {feature: FEATURE_LABELS[feature] for feature in active_features},
        "feature_values": {feature: FEATURE_VALUES[feature] for feature in active_features},
        "parameters": parameters,
        "map": {
            "width": MAP_WIDTH,
            "height": MAP_HEIGHT,
            "max_zoom": parameters["map_max_zoom"],
            "provinces": regions,
        },
        "guide": {
            "page_size": parameters["guide_page_size"],
            "provinces": guide_provinces,
        },
        "journey": {
            "panorama_width": PANORAMA_WIDTH,
            "panorama_height": PANORAMA_HEIGHT,
            "field_of_view_deg": 104,
            "landing_node": landing_node,
            "initial_yaw": initial_yaw,
            "nodes": journey_nodes,
            "step_budget": parameters["step_budget"],
        },
    }
    fingerprint = _world_fingerprint(public_contract)
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "status": "prototype_visual_candidate",
        "prompt": "Find the province, reconstruct the landing site, file every convention, and pin the original drop point.",
        "submit_label": "FILE LANDFALL",
        "asset_manifest": "shared_runtime/assets/provenance/unmarked_landfall_v0.json",
        "generator": {"name": GENERATOR_NAME, "variant_count": VARIANT_COUNT},
        "world_fingerprint": fingerprint,
        **copy.deepcopy(public_contract),
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "generator": {"name": GENERATOR_NAME, "variant_count": VARIANT_COUNT},
        "world_fingerprint": fingerprint,
        **copy.deepcopy(public_contract),
        "target": {
            "province_id": target_id,
            "signature": copy.deepcopy(target_signature),
            "landing_node": landing_node,
            "landing_point": {
                "x": float(landing_map_node["x"]),
                "y": float(landing_map_node["y"]),
            },
            "critical_features": critical_features,
            "solution_route": [f"road-{index}" for index in solution_walk],
        },
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    if interaction not in {"simplified", "full"}:
        raise ValueError("unsupported interaction mode")
    return public_state, ground_truth
