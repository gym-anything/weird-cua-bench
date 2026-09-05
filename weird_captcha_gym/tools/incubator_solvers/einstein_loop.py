from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MECHANIC_ID = "einstein_loop"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle(state_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _load_json(state_dir / "public_state.json"), _load_json(state_dir / "ground_truth.json")


def _centre(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise AssertionError("visible geometry has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _ordered_cycle(public: dict[str, Any], truth: dict[str, Any]) -> tuple[list[str], list[str]]:
    selected = set(truth["solution_edge_ids"])
    graph: dict[str, list[tuple[str, str]]] = {}
    for edge in public["puzzle"]["edges"]:
        if edge["id"] not in selected:
            continue
        start, end = edge["vertices"]
        graph.setdefault(start, []).append((end, edge["id"]))
        graph.setdefault(end, []).append((start, edge["id"]))
    if not graph or any(len(neighbours) != 2 for neighbours in graph.values()):
        raise AssertionError("private solution is not a cycle")
    start = min(graph, key=lambda value: int(value[1:]))
    vertices = [start]
    edges = []
    previous = None
    current = start
    while True:
        options = [item for item in graph[current] if item[0] != previous]
        following, edge_id = options[0]
        edges.append(edge_id)
        vertices.append(following)
        previous, current = current, following
        if current == start:
            break
        if len(edges) > len(selected):
            raise AssertionError("cycle traversal did not close")
    if set(edges) != selected:
        raise AssertionError("cycle traversal omitted solution edges")
    return vertices, edges


def _drag_path(page, vertex_ids: list[str]) -> None:
    points = [_centre(page.locator(f'[data-vertex-hit="{vertex_id}"]')) for vertex_id in vertex_ids]
    page.mouse.move(*points[0])
    page.mouse.down()
    for point in points[1:]:
        page.mouse.move(*point, steps=2)
    page.mouse.up()


def _click_edge(page, public: dict[str, Any], edge: dict[str, Any]) -> None:
    """Click the visible midpoint without asking Playwright to click a transparent hit line."""
    board = page.locator("[data-board]").bounding_box()
    if board is None:
        raise AssertionError("visible board has no bounding box")
    vertices = {vertex["id"]: vertex for vertex in public["puzzle"]["vertices"]}
    start, end = (vertices[vertex_id] for vertex_id in edge["vertices"])
    x = (start["x"] + end["x"]) / 2
    y = (start["y"] + end["y"]) / 2
    view_width = public["puzzle"]["view_width"]
    view_height = public["puzzle"]["view_height"]
    scale = min(board["width"] / view_width, board["height"] / view_height)
    inset_x = (board["width"] - view_width * scale) / 2
    inset_y = (board["height"] - view_height * scale) / 2
    page.mouse.click(
        board["x"] + inset_x + x * scale,
        board["y"] + inset_y + y * scale,
    )


def _mark_full(page, public: dict[str, Any], truth: dict[str, Any]) -> None:
    _vertices, ordered_edges = _ordered_cycle(public, truth)
    edges = {edge["id"]: edge for edge in public["puzzle"]["edges"]}
    for edge_id in ordered_edges:
        _drag_path(page, edges[edge_id]["vertices"])


def _mark_simplified(page, public: dict[str, Any], truth: dict[str, Any]) -> None:
    edges = {edge["id"]: edge for edge in public["puzzle"]["edges"]}
    for edge_id in truth["solution_edge_ids"]:
        _click_edge(page, public, edges[edge_id])
        page.locator('[data-proxy="loop"]').click()


def _wrong_edge(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    solution = set(truth["solution_edge_ids"])
    return next(edge for edge in public["puzzle"]["edges"] if edge["id"] not in solution)


def _fail_current(page, state_dir: Path) -> None:
    public, truth = _bundle(state_dir)
    interaction = (public.get("control_condition") or {}).get("interaction") or "full"
    wrong = _wrong_edge(public, truth)
    if interaction == "full":
        _drag_path(page, wrong["vertices"])
    elif interaction == "simplified":
        _click_edge(page, public, wrong)
        page.locator('[data-proxy="loop"]').click()
    else:
        raise AssertionError(f"unexpected interaction {interaction!r}")
    page.locator("[data-certify]").click()
    page.locator(".el-verdict.is-fail").wait_for(state="visible")


def _solve_current(page, state_dir: Path, *, certify: bool) -> None:
    public, truth = _bundle(state_dir)
    interaction = (public.get("control_condition") or {}).get("interaction") or "full"
    if interaction == "full":
        _mark_full(page, public, truth)
    elif interaction == "simplified":
        _mark_simplified(page, public, truth)
    else:
        raise AssertionError(f"unexpected interaction {interaction!r}")
    if certify:
        page.locator("[data-certify]").click()
        page.locator(".el-verdict.is-pass").wait_for(state="visible")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    _fail_current(page, state_dir)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    _solve_current(page, state_dir, certify=certify)
