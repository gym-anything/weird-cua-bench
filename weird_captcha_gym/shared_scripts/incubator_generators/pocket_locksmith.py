from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "pocket_locksmith"
ASSET_MANIFEST = "shared_runtime/assets/provenance/pocket_locksmith_v0.json"


def _seed_value(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:16], 16)


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _wrap_angle(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _norm(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in vector))
    if length < 1e-9:
        return [1.0, 0.0, 0.0]
    return [float(item) / length for item in vector]


def _cross(first: list[float], second: list[float]) -> list[float]:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _rotate(point: list[float], origin: list[float], axis: list[float], radians: float) -> list[float]:
    relative = [point[index] - origin[index] for index in range(3)]
    cosine = math.cos(radians)
    sine = math.sin(radians)
    cross = _cross(axis, relative)
    dot = sum(axis[index] * relative[index] for index in range(3))
    return [
        origin[index] + relative[index] * cosine + cross[index] * sine + axis[index] * dot * (1.0 - cosine)
        for index in range(3)
    ]


def forward_kinematics(base_points: list[list[float]], torsions: list[float]) -> list[list[float]]:
    """Rotate downstream atoms around each fixed bond, in chain order."""
    points = [[float(value) for value in point] for point in base_points]
    for bond_index, angle in enumerate(torsions):
        if bond_index + 2 >= len(points):
            break
        origin = points[bond_index]
        axis = _norm([points[bond_index + 1][axis] - origin[axis] for axis in range(3)])
        for point_index in range(bond_index + 2, len(points)):
            points[point_index] = _rotate(points[point_index], origin, axis, math.radians(float(angle)))
    return points


def _perpendicular(axis: list[float], sign: float) -> list[float]:
    reference = [0.0, 1.0, 0.0]
    candidate = _cross(axis, reference)
    if math.sqrt(sum(value * value for value in candidate)) < 1e-7:
        candidate = _cross(axis, [0.0, 0.0, 1.0])
    return [value * sign for value in _norm(candidate)]


def _inside(point: list[float], center: list[float], bounds: list[float], margin: float = 0.0) -> bool:
    return all(abs(point[index] - center[index]) <= bounds[index] - margin for index in range(3))


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((first[index] - second[index]) ** 2 for index in range(3)))


def _contact_site_candidates(
    rng: random.Random,
    target_points: list[list[float]],
    initial_points: list[list[float]],
    atom_index: int,
    radius: float,
    center: list[float],
    bounds: list[float],
) -> tuple[list[float], float]:
    """Choose a visible contact region that distinguishes target from start."""
    target = target_points[atom_index]
    previous = target_points[max(0, atom_index - 1)]
    axis = _norm([target[index] - previous[index] for index in range(3)])
    first = _perpendicular(axis, 1.0)
    second = _norm(_cross(axis, first))
    directions = [first, [-value for value in first], second, [-value for value in second]]
    for _ in range(24):
        directions.append(_norm([rng.uniform(-1.0, 1.0) for _ in range(3)]))
    offset = min(float(radius) * 0.86, 0.18)
    ranked: list[tuple[float, list[float]]] = []
    for direction in directions:
        candidate = [target[index] + direction[index] * offset for index in range(3)]
        if not _inside(candidate, center, bounds, 0.02):
            continue
        start_clearance = min((_distance(candidate, point) for point in initial_points), default=0.0)
        ranked.append((start_clearance, candidate))
    if not ranked:
        return list(target), 0.0
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1], ranked[0][0]


def _profile_parameters(condition: dict[str, Any] | None) -> dict[str, Any]:
    if condition:
        return dict(condition.get("difficulty_parameters") or {})
    # The uncontrolled task is the historical/reference L4 full configuration.
    return {
        "rotatable_bonds": 3,
        "pocket_obstacles": 5,
        "contact_count": 3,
        "torsion_step_deg": 15,
        "contact_tolerance": 0.22,
        "clearance_margin": 0.04,
        "handle_occlusion": True,
        "camera_step_deg": 18,
        "pocket_bounds": [3.35, 2.45, 2.35],
        "obstacle_radius": 0.22,
    }


def _make_obstacles(
    rng: random.Random,
    target_points: list[list[float]],
    atom_radius: float,
    obstacle_count: int,
    obstacle_radius: float,
    center: list[float],
    bounds: list[float],
    clearance: float,
) -> list[dict[str, Any]]:
    obstacles: list[dict[str, Any]] = []
    for index in range(obstacle_count):
        anchor_index = 1 + (index * 2) % max(1, len(target_points) - 1)
        anchor = target_points[anchor_index]
        if anchor_index + 1 < len(target_points):
            axis = _norm([target_points[anchor_index + 1][n] - anchor[n] for n in range(3)])
        else:
            axis = _norm([anchor[n] - target_points[anchor_index - 1][n] for n in range(3)])
        direction = _perpendicular(axis, -1.0 if rng.random() < 0.5 else 1.0)
        distance = atom_radius + obstacle_radius + clearance + rng.uniform(0.03, 0.09)
        candidate = [anchor[n] + direction[n] * distance for n in range(3)]
        if not _inside(candidate, center, bounds, obstacle_radius + 0.05):
            candidate = [anchor[n] - direction[n] * distance for n in range(3)]
        if not _inside(candidate, center, bounds, obstacle_radius + 0.05):
            candidate = [center[n] + rng.uniform(-bounds[n] * 0.7, bounds[n] * 0.7) for n in range(3)]
        for _ in range(24):
            if all(_distance(candidate, point) >= atom_radius + obstacle_radius + clearance for point in target_points):
                if all(_distance(candidate, item["center"]) >= obstacle_radius * 2.0 + clearance for item in obstacles):
                    break
            candidate = [center[n] + rng.uniform(-bounds[n] * 0.72, bounds[n] * 0.72) for n in range(3)]
        obstacles.append({
            "id": f"wall-{index + 1}",
            "center": [round(value, 4) for value in candidate],
            "radius": round(obstacle_radius, 4),
            "material": "pocket-wall" if index % 2 else "amber-contact-rim",
        })
    return obstacles


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    parameters = _profile_parameters(condition)
    rng = random.Random(_seed_value(seed))

    rotatable_bonds = int(parameters.get("rotatable_bonds", 3))
    atom_count = rotatable_bonds + 2
    step = float(parameters.get("torsion_step_deg", 15))
    obstacle_count = int(parameters.get("pocket_obstacles", 5))
    contact_count = int(parameters.get("contact_count", 3))
    atom_radius = 0.18
    obstacle_radius = float(parameters.get("obstacle_radius", 0.22))
    clearance = float(parameters.get("clearance_margin", 0.04))
    pocket_center = [0.22, 0.0, 0.0]
    pocket_bounds = [float(value) for value in parameters.get("pocket_bounds", [3.35, 2.45, 2.35])]

    base_points: list[list[float]] = []
    for index in range(atom_count):
        base_points.append([
            round(-1.56 + index * 0.78, 4),
            round(0.42 * math.sin(index * 1.45 + rng.uniform(-0.18, 0.18)), 4),
            round(0.34 * math.cos(index * 1.12 + rng.uniform(-0.18, 0.18)), 4),
        ])
    target_torsions = [
        float(rng.choice(tuple(range(-3, 4))) * step)
        for _ in range(rotatable_bonds)
    ]
    initial_torsions = []
    for target in target_torsions:
        # Keep the starting pose visibly separate from the marked contact
        # regions. A one-step offset can still sit inside the broad L1/L2
        # contact radius even though the target geometry is different.
        offset = rng.choice((-3, -2, 2, 3)) * step
        initial_torsions.append(_wrap_angle(target + offset))
    target_points = forward_kinematics(base_points, target_torsions)
    initial_points = forward_kinematics(base_points, initial_torsions)

    # The seed-specific pocket is built around the target conformation. Its
    # visible walls and independent replay geometry therefore agree exactly.
    obstacles = _make_obstacles(
        rng,
        target_points,
        atom_radius,
        obstacle_count,
        obstacle_radius,
        pocket_center,
        pocket_bounds,
        clearance,
    )

    # Contact markers belong to downstream atoms, never to the axis atom of
    # the first joint. Otherwise a marked site could remain occupied while a
    # torsion changes, making the starting pose look solved.
    candidate_atoms = list(range(2, atom_count))
    rng.shuffle(candidate_atoms)
    site_candidates = {
        atom_index: _contact_site_candidates(
            rng,
            target_points,
            initial_points,
            atom_index,
            float(parameters.get("contact_tolerance", 0.22)),
            pocket_center,
            pocket_bounds,
        )
        for atom_index in candidate_atoms
    }
    # Prefer target atoms whose visible contact region is not already occupied
    # by the starting conformation. This makes the initial board visibly
    # unsolved without adding a private final-pose predicate to grading.
    ranked_atoms = sorted(candidate_atoms, key=lambda index: site_candidates[index][1], reverse=True)
    contact_atoms = sorted(ranked_atoms[:contact_count])
    sites: list[dict[str, Any]] = []
    for site_index, atom_index in enumerate(contact_atoms):
        site_position = site_candidates[atom_index][0]
        sites.append({
            "id": f"site-{chr(65 + site_index)}",
            "label": chr(65 + site_index),
            "center": [round(value, 4) for value in site_position],
            "radius": round(float(parameters.get("contact_tolerance", 0.22)), 4),
            "color": ("#f5d36b", "#68e0c3", "#d69bff", "#ff8c69")[site_index % 4],
        })

    colors = {
        "C": "#dfe7f2",
        "N": "#6ec8ff",
        "O": "#ff7b73",
        "S": "#f5d36b",
    }
    elements = [rng.choice(("C", "N", "O", "S")) for _ in range(atom_count)]
    atoms = [
        {
            "id": f"atom-{index + 1}",
            "element": elements[index],
            "radius": atom_radius,
            "color": colors[elements[index]],
        }
        for index in range(atom_count)
    ]
    bonds = [
        {
            "id": f"bond-{index + 1}",
            "a": f"atom-{index + 1}",
            "b": f"atom-{index + 2}",
            "rotatable": index < rotatable_bonds,
        }
        for index in range(atom_count - 1)
    ]

    yaw_choices = (-72, -54, -36, -18, 0, 18, 36, 54, 72) if bool(parameters.get("handle_occlusion", True)) else (-24, -12, 0, 12, 24)
    pitch_choices = (-12, 0, 12) if bool(parameters.get("handle_occlusion", True)) else (-8, 0, 8)
    camera = {
        "yaw": float(rng.choice(yaw_choices)),
        "pitch": float(rng.choice(pitch_choices)),
        "distance": 7.1,
        "target": pocket_center,
        "focal": 570.0,
    }
    condition_token = ""
    if condition:
        condition_token = f"|d{condition.get('difficulty')}|{task.get('id')}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    prompt = task.get("natural_language") or "Orbit the pocket and rotate the connected key until it fits without clashes."
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "challenge_id": challenge_id,
        "prompt": prompt,
        "asset_manifest": ASSET_MANIFEST,
        "generator": {"name": "pocket_locksmith_kinematic_v1", "variant_count": 2**44},
        "view": {
            "canvas_width": 780,
            "canvas_height": 480,
            "camera_step_deg": float(parameters.get("camera_step_deg", 18)),
            "handle_lift": 0.34,
            "handle_radius": 0.23,
            "handle_occlusion": bool(parameters.get("handle_occlusion", True)),
        },
        "camera": camera,
        "pocket": {
            "center": pocket_center,
            "bounds": pocket_bounds,
            "obstacles": obstacles,
            "sites": sites,
            "shell_style": rng.choice(("smoked-quartz", "blue-amber", "violet-glass")),
        },
        "ligand": {
            "atoms": atoms,
            "bonds": bonds,
            "base_points": base_points,
            "initial_points": initial_points,
            "initial_torsions": initial_torsions,
        },
        "display": {
            "pocket_name": rng.choice(("ORCHID POCKET", "NACRE SOCKET", "LANTERN CAVITY", "MERCURY GROOVE")),
            "key_finish": rng.choice(("lapis", "citrine", "rose-gold", "verdigris")),
        },
    }
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_torsions": initial_torsions,
        "target_torsions": target_torsions,
        "base_points": base_points,
        "target_points": target_points,
        "atom_ids": [item["id"] for item in atoms],
        "atom_radius": atom_radius,
        "contacts": [
            {"site_id": site["id"], "atom_id": atoms[atom_index]["id"], "site_center": site["center"]}
            for site, atom_index in zip(sites, contact_atoms, strict=True)
        ],
        "obstacles": obstacles,
        "pocket_center": pocket_center,
        "pocket_bounds": pocket_bounds,
        "torsion_step_deg": step,
        "contact_tolerance": float(parameters.get("contact_tolerance", 0.22)),
        "clearance_margin": clearance,
        "camera_step_deg": float(parameters.get("camera_step_deg", 18)),
        "handle_lift": 0.34,
        "handle_radius": 0.23,
        "handle_occlusion": bool(parameters.get("handle_occlusion", True)),
        "variant_count": 2**44,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
