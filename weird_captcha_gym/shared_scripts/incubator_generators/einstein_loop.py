from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import deque
from typing import Any, Iterable


MECHANIC_ID = "einstein_loop"
SQRT3_OVER_2 = math.sqrt(3.0) / 2.0
VIEW_WIDTH = 960
VIEW_HEIGHT = 610


Point = tuple[float, float]
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _hex_point(x: float, y: float) -> Point:
    return (x + 0.5 * y, SQRT3_OVER_2 * y)


HAT_OUTLINE: tuple[Point, ...] = (
    _hex_point(0, 0),
    _hex_point(-1, -1),
    _hex_point(0, -2),
    _hex_point(2, -2),
    _hex_point(2, -1),
    _hex_point(4, -2),
    _hex_point(5, -1),
    _hex_point(4, 0),
    _hex_point(3, 0),
    _hex_point(2, 2),
    _hex_point(0, 3),
    _hex_point(0, 2),
    _hex_point(-1, 2),
)


class _Geometry:
    def __init__(self, shape: list[Point], label: str = "") -> None:
        self.shape = shape
        self.label = label
        self.children: list[tuple[Matrix, "_Geometry"]] = []

    def add(self, transform: Matrix, geometry: "_Geometry") -> None:
        self.children.append((transform, geometry))

    def eval_child(self, child: int, vertex: int) -> Point:
        transform, geometry = self.children[child]
        return _transform_point(transform, geometry.shape[vertex])

    def recentre(self) -> None:
        centre_x = sum(point[0] for point in self.shape) / len(self.shape)
        centre_y = sum(point[1] for point in self.shape) / len(self.shape)
        self.shape = [(x - centre_x, y - centre_y) for x, y in self.shape]
        shift = _translate(-centre_x, -centre_y)
        self.children = [(_multiply(shift, transform), geometry) for transform, geometry in self.children]


def _transform_point(transform: Matrix, point: Point) -> Point:
    return (
        transform[0] * point[0] + transform[1] * point[1] + transform[2],
        transform[3] * point[0] + transform[4] * point[1] + transform[5],
    )


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    return (
        left[0] * right[0] + left[1] * right[3],
        left[0] * right[1] + left[1] * right[4],
        left[0] * right[2] + left[1] * right[5] + left[2],
        left[3] * right[0] + left[4] * right[3],
        left[3] * right[1] + left[4] * right[4],
        left[3] * right[2] + left[4] * right[5] + left[5],
    )


def _inverse(transform: Matrix) -> Matrix:
    determinant = transform[0] * transform[4] - transform[1] * transform[3]
    return (
        transform[4] / determinant,
        -transform[1] / determinant,
        (transform[1] * transform[5] - transform[2] * transform[4]) / determinant,
        -transform[3] / determinant,
        transform[0] / determinant,
        (transform[2] * transform[3] - transform[0] * transform[5]) / determinant,
    )


def _translate(x: float, y: float) -> Matrix:
    return (1.0, 0.0, x, 0.0, 1.0, y)


def _rotate(angle: float) -> Matrix:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (cosine, -sine, 0.0, sine, cosine, 0.0)


def _rotate_about(point: Point, angle: float) -> Matrix:
    return _multiply(_translate(*point), _multiply(_rotate(angle), _translate(-point[0], -point[1])))


def _match_segment(start: Point, end: Point) -> Matrix:
    return (
        end[0] - start[0],
        start[1] - end[1],
        start[0],
        end[1] - start[1],
        end[0] - start[0],
        start[1],
    )


def _match_two(source_start: Point, source_end: Point, target_start: Point, target_end: Point) -> Matrix:
    return _multiply(_match_segment(target_start, target_end), _inverse(_match_segment(source_start, source_end)))


def _add(left: Point, right: Point) -> Point:
    return (left[0] + right[0], left[1] + right[1])


def _subtract(left: Point, right: Point) -> Point:
    return (left[0] - right[0], left[1] - right[1])


def _intersection(p1: Point, q1: Point, p2: Point, q2: Point) -> Point:
    denominator = (q2[1] - p2[1]) * (q1[0] - p1[0]) - (q2[0] - p2[0]) * (q1[1] - p1[1])
    factor = ((q2[0] - p2[0]) * (p1[1] - p2[1]) - (q2[1] - p2[1]) * (p1[0] - p2[0])) / denominator
    return (p1[0] + factor * (q1[0] - p1[0]), p1[1] + factor * (q1[1] - p1[1]))


def _initial_metatiles() -> tuple[_Geometry, _Geometry, _Geometry, _Geometry]:
    leaves = {label: _Geometry(list(HAT_OUTLINE), label=label) for label in ("H1", "H", "T", "P", "F")}

    h_outline = [
        (0.0, 0.0),
        (4.0, 0.0),
        (4.5, SQRT3_OVER_2),
        (2.5, 5 * SQRT3_OVER_2),
        (1.5, 5 * SQRT3_OVER_2),
        (-0.5, SQRT3_OVER_2),
    ]
    h_meta = _Geometry(h_outline)
    h_meta.add(_match_two(HAT_OUTLINE[5], HAT_OUTLINE[7], h_outline[5], h_outline[0]), leaves["H"])
    h_meta.add(_match_two(HAT_OUTLINE[9], HAT_OUTLINE[11], h_outline[1], h_outline[2]), leaves["H"])
    h_meta.add(_match_two(HAT_OUTLINE[5], HAT_OUTLINE[7], h_outline[3], h_outline[4]), leaves["H"])
    h_meta.add(
        _multiply(
            _translate(2.5, SQRT3_OVER_2),
            _multiply((-0.5, -SQRT3_OVER_2, 0.0, SQRT3_OVER_2, -0.5, 0.0), (0.5, 0.0, 0.0, 0.0, -0.5, 0.0)),
        ),
        leaves["H1"],
    )

    t_outline = [(0.0, 0.0), (3.0, 0.0), (1.5, 3 * SQRT3_OVER_2)]
    t_meta = _Geometry(t_outline)
    t_meta.add((0.5, 0.0, 0.5, 0.0, 0.5, SQRT3_OVER_2), leaves["T"])

    p_outline = [(0.0, 0.0), (4.0, 0.0), (3.0, 2 * SQRT3_OVER_2), (-1.0, 2 * SQRT3_OVER_2)]
    p_meta = _Geometry(p_outline)
    p_meta.add((0.5, 0.0, 1.5, 0.0, 0.5, SQRT3_OVER_2), leaves["P"])
    p_meta.add(
        _multiply(
            _translate(0.0, 2 * SQRT3_OVER_2),
            _multiply((0.5, SQRT3_OVER_2, 0.0, -SQRT3_OVER_2, 0.5, 0.0), (0.5, 0.0, 0.0, 0.0, 0.5, 0.0)),
        ),
        leaves["P"],
    )

    f_outline = [(0.0, 0.0), (3.0, 0.0), (3.5, SQRT3_OVER_2), (3.0, 2 * SQRT3_OVER_2), (-1.0, 2 * SQRT3_OVER_2)]
    f_meta = _Geometry(f_outline)
    f_meta.add((0.5, 0.0, 1.5, 0.0, 0.5, SQRT3_OVER_2), leaves["F"])
    f_meta.add(
        _multiply(
            _translate(0.0, 2 * SQRT3_OVER_2),
            _multiply((0.5, SQRT3_OVER_2, 0.0, -SQRT3_OVER_2, 0.5, 0.0), (0.5, 0.0, 0.0, 0.0, 0.5, 0.0)),
        ),
        leaves["F"],
    )
    return h_meta, t_meta, p_meta, f_meta


def _construct_patch(h_meta: _Geometry, t_meta: _Geometry, p_meta: _Geometry, f_meta: _Geometry) -> _Geometry:
    rules: tuple[tuple[Any, ...], ...] = (
        ("H",), (0, 0, "P", 2), (1, 0, "H", 2), (2, 0, "P", 2), (3, 0, "H", 2),
        (4, 4, "P", 2), (0, 4, "F", 3), (2, 4, "F", 3), (4, 1, 3, 2, "F", 0),
        (8, 3, "H", 0), (9, 2, "P", 0), (10, 2, "H", 0), (11, 4, "P", 2),
        (12, 0, "H", 2), (13, 0, "F", 3), (14, 2, "F", 1), (15, 3, "H", 4),
        (8, 2, "F", 1), (17, 3, "H", 0), (18, 2, "P", 0), (19, 2, "H", 2),
        (20, 4, "F", 3), (20, 0, "P", 2), (22, 0, "H", 2), (23, 4, "F", 3),
        (23, 0, "F", 3), (16, 0, "P", 2), (9, 4, 0, 2, "T", 2), (4, 0, "F", 3),
    )
    shapes = {"H": h_meta, "T": t_meta, "P": p_meta, "F": f_meta}
    patch = _Geometry([])
    for rule in rules:
        if len(rule) == 1:
            patch.add(IDENTITY, shapes[rule[0]])
        elif len(rule) == 4:
            parent_transform, parent_geometry = patch.children[rule[0]]
            target_start = _transform_point(parent_transform, parent_geometry.shape[(rule[1] + 1) % len(parent_geometry.shape)])
            target_end = _transform_point(parent_transform, parent_geometry.shape[rule[1]])
            geometry = shapes[rule[2]]
            patch.add(_match_two(geometry.shape[rule[3]], geometry.shape[(rule[3] + 1) % len(geometry.shape)], target_start, target_end), geometry)
        else:
            transform_p, geometry_p = patch.children[rule[0]]
            transform_q, geometry_q = patch.children[rule[2]]
            target_start = _transform_point(transform_q, geometry_q.shape[rule[3]])
            target_end = _transform_point(transform_p, geometry_p.shape[rule[1]])
            geometry = shapes[rule[4]]
            patch.add(_match_two(geometry.shape[rule[5]], geometry.shape[(rule[5] + 1) % len(geometry.shape)], target_start, target_end), geometry)
    return patch


def _construct_metatiles(patch: _Geometry) -> tuple[_Geometry, _Geometry, _Geometry, _Geometry]:
    base_start = patch.eval_child(8, 2)
    base_end = patch.eval_child(21, 2)
    rotated_base = _transform_point(_rotate_about(base_start, -2 * math.pi / 3), base_end)
    point_72 = patch.eval_child(7, 2)
    point_252 = patch.eval_child(25, 2)
    lower_left = _intersection(base_start, rotated_base, patch.eval_child(6, 2), point_72)
    vector = _subtract(patch.eval_child(6, 2), lower_left)

    h_outline = [lower_left, base_start]
    vector = _transform_point(_rotate(-math.pi / 3), vector)
    h_outline.append(_add(h_outline[1], vector))
    h_outline.append(patch.eval_child(14, 2))
    vector = _transform_point(_rotate(-math.pi / 3), vector)
    h_outline.append(_subtract(h_outline[3], vector))
    h_outline.append(patch.eval_child(6, 2))
    new_h = _Geometry(h_outline)
    for child in (0, 9, 16, 27, 26, 6, 1, 8, 10, 15):
        new_h.add(*patch.children[child])

    p_outline = [point_72, _add(point_72, _subtract(base_start, lower_left)), base_start, lower_left]
    new_p = _Geometry(p_outline)
    for child in (7, 2, 3, 4, 28):
        new_p.add(*patch.children[child])

    f_outline = [base_end, patch.eval_child(24, 2), patch.eval_child(25, 0), point_252, _add(point_252, _subtract(lower_left, base_start))]
    new_f = _Geometry(f_outline)
    for child in (21, 20, 22, 23, 24, 25):
        new_f.add(*patch.children[child])

    point_a = h_outline[2]
    point_b = _add(h_outline[1], _subtract(h_outline[4], h_outline[5]))
    point_c = _transform_point(_rotate_about(point_b, -math.pi / 3), point_a)
    new_t = _Geometry([point_b, point_c, point_a])
    new_t.add(*patch.children[11])

    for geometry in (new_h, new_t, new_p, new_f):
        geometry.recentre()
    return new_h, new_t, new_p, new_f


def _flatten(geometry: _Geometry, transform: Matrix = IDENTITY) -> list[dict[str, Any]]:
    if not geometry.children:
        points = [_transform_point(transform, point) for point in geometry.shape]
        # The geometric hat silhouette has 13 sides, one twice the elementary
        # boundary length.  In the substitution tiling that side can meet two
        # neighbouring sides.  Preserve the silhouette while inserting the
        # real junction so every visible/clickable graph edge is atomic.
        lengths = [math.dist(points[index], points[(index + 1) % len(points)]) for index in range(len(points))]
        longest = max(range(len(points)), key=lengths.__getitem__)
        if lengths[longest] < min(lengths) * 1.9:
            raise RuntimeError("hat outline has no subdividable double side")
        end = points[(longest + 1) % len(points)]
        midpoint = ((points[longest][0] + end[0]) / 2, (points[longest][1] + end[1]) / 2)
        points.insert(longest + 1, midpoint)
        return [{"label": geometry.label, "points": points}]
    result: list[dict[str, Any]] = []
    for child_transform, child in geometry.children:
        result.extend(_flatten(child, _multiply(transform, child_transform)))
    return result


def _hat_pool() -> list[dict[str, Any]]:
    metatiles = _initial_metatiles()
    for _ in range(2):
        metatiles = _construct_metatiles(_construct_patch(*metatiles))
    pool: list[dict[str, Any]] = []
    for family, geometry in zip(("H", "T", "P", "F"), metatiles):
        for tile in _flatten(geometry):
            tile["family"] = family
            pool.append(tile)
    unique: dict[tuple[tuple[float, float], ...], dict[str, Any]] = {}
    for tile in pool:
        key = tuple((round(point[0], 6), round(point[1], 6)) for point in tile["points"])
        unique.setdefault(key, tile)
    return list(unique.values())


_TILE_POOL = _hat_pool()


def _edge_key(start: Point, end: Point) -> tuple[Point, Point]:
    first = (round(start[0], 6), round(start[1], 6))
    second = (round(end[0], 6), round(end[1], 6))
    return tuple(sorted((first, second)))  # type: ignore[return-value]


def _tile_adjacency(tiles: list[dict[str, Any]]) -> tuple[list[set[int]], dict[tuple[Point, Point], list[int]]]:
    owners: dict[tuple[Point, Point], list[int]] = {}
    for face_index, tile in enumerate(tiles):
        points = tile["points"]
        for index, start in enumerate(points):
            owners.setdefault(_edge_key(start, points[(index + 1) % len(points)]), []).append(face_index)
    adjacency = [set() for _ in tiles]
    for faces in owners.values():
        if len(faces) == 2:
            adjacency[faces[0]].add(faces[1])
            adjacency[faces[1]].add(faces[0])
    return adjacency, owners


def _connected_patch(rng: random.Random, tile_count: int) -> list[dict[str, Any]]:
    adjacency, _ = _tile_adjacency(_TILE_POOL)
    eligible = [index for index, neighbours in enumerate(adjacency) if len(neighbours) >= 2]
    for _ in range(500):
        start = rng.choice(eligible)
        chosen = [start]
        chosen_set = {start}
        frontier = set(adjacency[start])
        while len(chosen) < tile_count and frontier:
            candidates = sorted(frontier)
            rng.shuffle(candidates)
            candidates.sort(key=lambda item: len(adjacency[item] & chosen_set), reverse=True)
            item = rng.choice(candidates[: min(4, len(candidates))])
            frontier.discard(item)
            if item in chosen_set:
                continue
            chosen.append(item)
            chosen_set.add(item)
            frontier.update(adjacency[item] - chosen_set)
        if len(chosen) == tile_count:
            return [copy.deepcopy(_TILE_POOL[index]) for index in chosen]
    raise RuntimeError("could not crop a connected hat patch")


def _point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing = (previous[0] - current[0]) * (point[1] - current[1]) / (previous[1] - current[1]) + current[0]
            if point[0] < crossing:
                inside = not inside
        previous = current
    return inside


def _segment_distance(point: Point, start: Point, end: Point) -> float:
    delta_x, delta_y = end[0] - start[0], end[1] - start[1]
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator == 0:
        return math.dist(point, start)
    fraction = max(0.0, min(1.0, ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / denominator))
    projection = (start[0] + fraction * delta_x, start[1] + fraction * delta_y)
    return math.dist(point, projection)


def _label_point(polygon: list[Point]) -> Point:
    minimum_x = min(point[0] for point in polygon)
    maximum_x = max(point[0] for point in polygon)
    minimum_y = min(point[1] for point in polygon)
    maximum_y = max(point[1] for point in polygon)
    candidates = [(sum(point[0] for point in polygon) / len(polygon), sum(point[1] for point in polygon) / len(polygon))]
    for row in range(1, 12):
        for col in range(1, 12):
            candidates.append((minimum_x + (maximum_x - minimum_x) * col / 12, minimum_y + (maximum_y - minimum_y) * row / 12))
    valid = [point for point in candidates if _point_in_polygon(point, polygon)]
    return max(valid, key=lambda point: min(_segment_distance(point, polygon[index], polygon[(index + 1) % len(polygon)]) for index in range(len(polygon))))


def _normalise_patch(tiles: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    angle = rng.randrange(6) * math.pi / 3
    mirror = -1.0 if rng.randrange(2) else 1.0
    transform: Matrix = (mirror * math.cos(angle), -math.sin(angle), 0.0, mirror * math.sin(angle), math.cos(angle), 0.0)
    transformed = [[_transform_point(transform, point) for point in tile["points"]] for tile in tiles]
    all_points = [point for polygon in transformed for point in polygon]
    minimum_x, maximum_x = min(point[0] for point in all_points), max(point[0] for point in all_points)
    minimum_y, maximum_y = min(point[1] for point in all_points), max(point[1] for point in all_points)
    scale = min((VIEW_WIDTH - 70) / (maximum_x - minimum_x), (VIEW_HEIGHT - 70) / (maximum_y - minimum_y))
    offset_x = (VIEW_WIDTH - (maximum_x - minimum_x) * scale) / 2 - minimum_x * scale
    offset_y = (VIEW_HEIGHT - (maximum_y - minimum_y) * scale) / 2 - minimum_y * scale
    polygons = [[(point[0] * scale + offset_x, point[1] * scale + offset_y) for point in polygon] for polygon in transformed]

    vertex_lookup: dict[Point, str] = {}
    vertices: list[dict[str, Any]] = []

    def vertex_id(point: Point) -> str:
        key = (round(point[0], 3), round(point[1], 3))
        if key not in vertex_lookup:
            identifier = f"v{len(vertices)}"
            vertex_lookup[key] = identifier
            vertices.append({"id": identifier, "x": key[0], "y": key[1]})
        return vertex_lookup[key]

    faces: list[dict[str, Any]] = []
    edge_lookup: dict[tuple[str, str], str] = {}
    edges: list[dict[str, Any]] = []
    for face_index, (tile, polygon) in enumerate(zip(tiles, polygons)):
        ids = [vertex_id(point) for point in polygon]
        face_edge_ids = []
        face_id = f"f{face_index}"
        for index, start in enumerate(ids):
            end = ids[(index + 1) % len(ids)]
            key = tuple(sorted((start, end)))
            if key not in edge_lookup:
                identifier = f"e{len(edges)}"
                edge_lookup[key] = identifier
                edges.append({"id": identifier, "vertices": [start, end], "faces": [face_id]})
            else:
                identifier = edge_lookup[key]
                edges[int(identifier[1:])]["faces"].append(face_id)
            face_edge_ids.append(identifier)
        label_x, label_y = _label_point(polygon)
        faces.append({
            "id": face_id,
            "vertices": ids,
            "edge_ids": face_edge_ids,
            "label_point": {"x": round(label_x, 3), "y": round(label_y, 3)},
            "tone": (face_index + rng.randrange(3)) % 5,
            "orientation_class": tile["label"],
        })
    return {"view_width": VIEW_WIDTH, "view_height": VIEW_HEIGHT, "vertices": vertices, "edges": edges, "faces": faces}


def _single_cycle(edge_ids: Iterable[str], puzzle: dict[str, Any]) -> bool:
    selected = set(edge_ids)
    if len(selected) < 3:
        return False
    adjacency: dict[str, list[str]] = {}
    for edge in puzzle["edges"]:
        if edge["id"] not in selected:
            continue
        start, end = edge["vertices"]
        adjacency.setdefault(start, []).append(end)
        adjacency.setdefault(end, []).append(start)
    if not adjacency or any(len(neighbours) != 2 for neighbours in adjacency.values()):
        return False
    seen = set()
    queue = [next(iter(adjacency))]
    while queue:
        vertex = queue.pop()
        if vertex in seen:
            continue
        seen.add(vertex)
        queue.extend(adjacency[vertex])
    return len(seen) == len(adjacency)


def _solution_boundary(rng: random.Random, puzzle: dict[str, Any], minimum_internal: int) -> set[str]:
    face_edges = {face["id"]: set(face["edge_ids"]) for face in puzzle["faces"]}
    edge_faces = {edge["id"]: edge["faces"] for edge in puzzle["edges"]}
    neighbours = {face_id: set() for face_id in face_edges}
    for faces in edge_faces.values():
        if len(faces) == 2:
            neighbours[faces[0]].add(faces[1])
            neighbours[faces[1]].add(faces[0])
    face_ids = list(face_edges)
    for _ in range(800):
        inside_target = rng.randint(max(2, len(face_ids) // 3), max(3, (len(face_ids) * 2) // 3))
        start = rng.choice(face_ids)
        inside = {start}
        frontier = set(neighbours[start])
        while len(inside) < inside_target and frontier:
            options = sorted(frontier, key=lambda value: int(value[1:]))
            rng.shuffle(options)
            options.sort(key=lambda face: len(neighbours[face] & inside), reverse=True)
            chosen = rng.choice(options[: min(3, len(options))])
            inside.add(chosen)
            frontier.discard(chosen)
            frontier.update(neighbours[chosen] - inside)
        boundary = {
            edge_id
            for edge_id, owners in edge_faces.items()
            if sum(owner in inside for owner in owners) == 1
        }
        internal = sum(1 for edge_id in boundary if len(edge_faces[edge_id]) == 2)
        if internal >= minimum_internal and _single_cycle(boundary, puzzle):
            return boundary
    raise RuntimeError("could not generate a nontrivial single loop on the hat patch")


class _SearchLimit(RuntimeError):
    pass


def _count_solutions(puzzle: dict[str, Any], clues: dict[str, int], *, limit: int = 2, node_limit: int = 120_000) -> tuple[int, set[str] | None]:
    edge_ids = [edge["id"] for edge in puzzle["edges"]]
    edge_index = {edge_id: index for index, edge_id in enumerate(edge_ids)}
    face_edges = {face["id"]: [edge_index[edge_id] for edge_id in face["edge_ids"]] for face in puzzle["faces"]}
    vertex_edges: dict[str, list[int]] = {vertex["id"]: [] for vertex in puzzle["vertices"]}
    edge_vertices = []
    for index, edge in enumerate(puzzle["edges"]):
        edge_vertices.append(tuple(edge["vertices"]))
        for vertex in edge["vertices"]:
            vertex_edges[vertex].append(index)
    nodes = 0
    first_solution: set[str] | None = None

    def assign(state: list[int], edge: int, value: int) -> bool:
        if state[edge] not in (-1, value):
            return False
        state[edge] = value
        return True

    def propagate(state: list[int]) -> bool:
        changed = True
        while changed:
            changed = False
            for face_id, clue in clues.items():
                indices = face_edges[face_id]
                selected = sum(state[index] == 1 for index in indices)
                unknown = [index for index in indices if state[index] == -1]
                if selected > clue or selected + len(unknown) < clue:
                    return False
                forced = None
                if selected == clue:
                    forced = 0
                elif selected + len(unknown) == clue:
                    forced = 1
                if forced is not None:
                    for index in unknown:
                        if not assign(state, index, forced):
                            return False
                        changed = True
            for indices in vertex_edges.values():
                selected = sum(state[index] == 1 for index in indices)
                unknown = [index for index in indices if state[index] == -1]
                if selected > 2 or selected == 1 and not unknown:
                    return False
                forced = None
                if selected == 2:
                    forced = 0
                elif selected == 1 and len(unknown) == 1:
                    forced = 1
                elif selected == 0 and len(unknown) == 1:
                    forced = 0
                if forced is not None:
                    for index in unknown:
                        if not assign(state, index, forced):
                            return False
                        changed = True

            selected_indices = [index for index, value in enumerate(state) if value == 1]
            if selected_indices:
                graph: dict[str, list[str]] = {}
                for index in selected_indices:
                    start, end = edge_vertices[index]
                    graph.setdefault(start, []).append(end)
                    graph.setdefault(end, []).append(start)
                seen: set[str] = set()
                closed_component: set[str] | None = None
                for vertex in graph:
                    if vertex in seen:
                        continue
                    component = set()
                    stack = [vertex]
                    while stack:
                        current = stack.pop()
                        if current in component:
                            continue
                        component.add(current)
                        stack.extend(graph[current])
                    seen.update(component)
                    if all(len(graph[item]) == 2 for item in component):
                        closed_component = component
                        break
                if closed_component is not None:
                    if any(vertex not in closed_component for vertex in graph):
                        return False
                    for index, value in enumerate(state):
                        if value == -1:
                            state[index] = 0
                            changed = True
        return True

    def branch_score(index: int, state: list[int]) -> tuple[int, int]:
        start, end = edge_vertices[index]
        selected_neighbours = sum(state[other] == 1 for vertex in (start, end) for other in vertex_edges[vertex])
        clue_pressure = 0
        edge_id = edge_ids[index]
        owners = next(edge["faces"] for edge in puzzle["edges"] if edge["id"] == edge_id)
        for owner in owners:
            if owner in clues:
                clue_pressure += 20 - len([other for other in face_edges[owner] if state[other] == -1])
        return selected_neighbours, clue_pressure

    def search(state: list[int]) -> int:
        nonlocal nodes, first_solution
        nodes += 1
        if nodes > node_limit:
            raise _SearchLimit("loop uniqueness search exceeded its node budget")
        if not propagate(state):
            return 0
        unknown = [index for index, value in enumerate(state) if value == -1]
        if not unknown:
            selected = {edge_ids[index] for index, value in enumerate(state) if value == 1}
            if not _single_cycle(selected, puzzle):
                return 0
            first_solution = first_solution or selected
            return 1
        edge = max(unknown, key=lambda index: branch_score(index, state))
        total = 0
        for value in (1, 0):
            candidate = state.copy()
            candidate[edge] = value
            total += search(candidate)
            if total >= limit:
                return total
        return total

    return search([-1] * len(edge_ids)), first_solution


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return {
        "tile_count": 13,
        "clue_fraction": 0.68,
        "minimum_internal_loop_edges": 5,
    }


def _validate(parameters: dict[str, Any]) -> None:
    tile_count = parameters.get("tile_count")
    internal = parameters.get("minimum_internal_loop_edges")
    clue_fraction = parameters.get("clue_fraction")
    if isinstance(tile_count, bool) or not isinstance(tile_count, int) or not 6 <= tile_count <= 24:
        raise ValueError("tile_count must be an integer in [6, 24]")
    if isinstance(internal, bool) or not isinstance(internal, int) or not 1 <= internal <= 16:
        raise ValueError("minimum_internal_loop_edges must be an integer in [1, 16]")
    if isinstance(clue_fraction, bool) or not isinstance(clue_fraction, (int, float)) or not 0.35 <= float(clue_fraction) <= 1.0:
        raise ValueError("clue_fraction must be a number in [0.35, 1.0]")


def _build_puzzle(rng: random.Random, parameters: dict[str, Any]) -> tuple[dict[str, Any], set[str], dict[str, Any]]:
    target_clues = max(3, math.ceil(parameters["tile_count"] * float(parameters["clue_fraction"])))
    for attempt in range(260):
        tiles = _connected_patch(rng, parameters["tile_count"])
        puzzle = _normalise_patch(tiles, rng)
        if any(len(edge["faces"]) > 2 for edge in puzzle["edges"]):
            continue
        try:
            solution = _solution_boundary(rng, puzzle, parameters["minimum_internal_loop_edges"])
        except RuntimeError:
            continue
        all_clues = {
            face["id"]: sum(edge_id in solution for edge_id in face["edge_ids"])
            for face in puzzle["faces"]
        }
        try:
            count, found = _count_solutions(puzzle, all_clues)
        except _SearchLimit:
            continue
        if count != 1 or found != solution:
            continue
        kept = set(all_clues)
        removable = sorted(kept, key=lambda value: int(value[1:]))
        rng.shuffle(removable)
        for face_id in removable:
            if len(kept) <= target_clues:
                break
            candidate = kept - {face_id}
            try:
                candidate_count, candidate_solution = _count_solutions(
                    puzzle,
                    {key: all_clues[key] for key in sorted(candidate, key=lambda value: int(value[1:]))},
                )
            except _SearchLimit:
                continue
            if candidate_count == 1 and candidate_solution == solution:
                kept = candidate
        if len(kept) > target_clues:
            continue
        clues = [{"face_id": face_id, "value": all_clues[face_id]} for face_id in sorted(kept, key=lambda value: int(value[1:]))]
        puzzle["clues"] = clues
        profile = {
            "attempt": attempt + 1,
            "tile_count": len(puzzle["faces"]),
            "edge_count": len(puzzle["edges"]),
            "vertex_count": len(puzzle["vertices"]),
            "clue_count": len(clues),
            "solution_edge_count": len(solution),
            "internal_solution_edges": sum(
                1 for edge in puzzle["edges"] if edge["id"] in solution and len(edge["faces"]) == 2
            ),
            "unique_solution_count": 1,
        }
        return puzzle, solution, profile
    raise RuntimeError("could not generate a uniquely solvable Einstein Loop inside the requested profile")


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    parameter_token = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameter_token}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    puzzle, solution, generation_profile = _build_puzzle(rng, parameters)
    task_id = str(task.get("id") or MECHANIC_ID)
    challenge_id = f"el-{stable[:18]}"
    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "ONE LOOP. EACH NUMBER COUNTS ITS VISIBLE TILE EDGES.",
        "puzzle": copy.deepcopy(puzzle),
        "parameters": copy.deepcopy(parameters),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/einstein_loop_v0.json"),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "puzzle": copy.deepcopy(puzzle),
        "parameters": copy.deepcopy(parameters),
        "solution_edge_ids": sorted(solution, key=lambda value: int(value[1:])),
        "generation_profile": generation_profile,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


__all__ = ["MECHANIC_ID", "generate", "_count_solutions", "_single_cycle"]
