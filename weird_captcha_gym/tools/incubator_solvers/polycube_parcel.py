"""Ordinary-input construction witness for Polycube Parcel.

The witness reads the private exact-cover solution only to choose legal visible
camera, rotation, and placement actions. It never mutates browser state.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections import deque

from playwright.sync_api import expect


MECHANIC_ID = "polycube_parcel"
ROTATIONS = {
    ("x", 1): [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
    ("x", -1): [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
    ("y", 1): [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
    ("y", -1): [[0, 0, -1], [0, 1, 0], [1, 0, 0]],
    ("z", 1): [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    ("z", -1): [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
}


def _mul(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _vec(m: list[list[int]], v: list[float]) -> list[float]:
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def _cells(piece: dict, orientation: list[list[int]], origin: list[float]) -> list[list[float]]:
    return [[_vec(orientation, cell)[axis] + float(origin[axis]) for axis in range(3)] for cell in piece["shape"]]


def _project(point: list[float], camera: dict) -> dict[str, float]:
    import math
    yaw = float(camera["yaw"]) * math.pi / 180.0
    pitch = float(camera["pitch"])
    x, y, z = map(float, point)
    rx = x * math.cos(yaw) - z * math.sin(yaw)
    rz = x * math.sin(yaw) + z * math.cos(yaw)
    py = y * math.cos(pitch) - rz * math.sin(pitch)
    depth = y * math.sin(pitch) + rz * math.cos(pitch)
    return {"x": 460.0 + rx * 68.0, "y": 326.0 - py * 68.0, "depth": depth}


def _centroid(points: list[list[float]]) -> list[float]:
    return [sum(point[axis] for point in points) / len(points) for axis in range(3)]


def _orientation_path(start: list[list[int]], target: list[list[int]]) -> list[tuple[str, int]]:
    start_key = tuple(tuple(row) for row in start)
    target_key = tuple(tuple(row) for row in target)
    queue = deque([(start_key, [])])
    visited = {start_key}
    while queue:
        current, path = queue.popleft()
        if current == target_key:
            return path
        current_list = [list(row) for row in current]
        for action, rotation in ROTATIONS.items():
            next_matrix = _mul(rotation, current_list)
            next_key = tuple(tuple(row) for row in next_matrix)
            if next_key not in visited:
                visited.add(next_key)
                queue.append((next_key, path + [action]))
    raise AssertionError("orientation path was not found")


def _screen_point(box: dict, point: dict[str, float]) -> tuple[float, float]:
    return box["x"] + point["x"] * box["width"] / 920.0, box["y"] + point["y"] * box["height"] / 560.0


def _camera_orbit(page, interaction: str, camera: dict) -> dict:
    if interaction == "simplified":
        page.locator('[data-camera="left"]').click()
        page.locator('[data-camera="up"]').click()
        camera["yaw"] = (float(camera["yaw"]) - 24.0) % 360.0
        camera["pitch"] = max(0.18, float(camera["pitch"]) - 0.10)
        return camera
    stage = page.locator(".pp-stage")
    box = stage.bounding_box()
    assert box, "parcel stage has no bounding box"
    start = (box["x"] + box["width"] * 0.78, box["y"] + box["height"] * 0.82)
    finish = (start[0] + 82, start[1] + 18)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*finish, steps=10)
    page.mouse.up()
    # The browser converts CSS-pixel motion to viewBox motion before applying
    # its camera increments.  Mirror that conversion so subsequent visible
    # drop coordinates remain aligned with the rendered scene.
    delta_x = 82.0 * 920.0 / box["width"]
    delta_y = 18.0 * 560.0 / box["height"]
    camera["yaw"] = (float(camera["yaw"]) + delta_x * 0.55) % 360.0
    camera["pitch"] = max(0.18, min(0.82, float(camera["pitch"]) + delta_y * 0.004))
    return camera


def _select(page, piece_id: str) -> None:
    # The piece ledger is a visible, unambiguous control even when loose
    # geometry projects over the translucent parcel.
    locator = page.locator(f'.pp-piece-row[data-piece-row="{piece_id}"]')
    expect(locator).to_be_visible(timeout=3000)
    locator.click()


def _rotate(page, piece: dict, target: list[list[int]]) -> None:
    for axis, direction in _orientation_path(piece["orientation"], target):
        page.locator(f".pp-rotate-{axis}-{'plus' if direction > 0 else 'minus'}").click()
        piece["orientation"] = _mul(ROTATIONS[(axis, direction)], piece["orientation"])


def _place_simplified(page, piece: dict, origin: list[int]) -> None:
    for axis, value in zip(("x", "y", "z"), origin):
        page.locator(f".pp-origin-{axis}").select_option(str(int(value)))
    page.locator(".pp-place-proxy").click()
    piece["origin"] = list(origin)
    piece["placed"] = True


def _place_full(page, piece: dict, target_cells: list[list[int]], target_origin: list[int], camera: dict) -> None:
    stage = page.locator(".pp-stage")
    box = stage.bounding_box()
    assert box, "parcel stage has no bounding box"
    # Match the browser's lattice-centroid calculation exactly (it uses the
    # integer cell coordinates rather than adding a half-cell visual offset).
    target_point = _project(_centroid(target_cells), camera)
    # Start on an actual rendered face rather than the mathematical centroid;
    # a concave polycube can have a centroid in empty space.
    face = page.locator(f'.pp-piece[data-piece-id="{piece["id"]}"] .pp-piece-face').first
    face_box = face.bounding_box()
    assert face_box, f"piece {piece['id']} has no rendered face"
    start = (face_box["x"] + face_box["width"] / 2, face_box["y"] + face_box["height"] / 2)
    finish = _screen_point(box, target_point)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*finish, steps=14)
    page.mouse.up()
    piece["origin"] = list(target_origin)
    piece["placed"] = True


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    del mechanic
    before = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    page.locator(".pp-abandon").click()
    expect(page.locator(".pp-readout")).to_contain_text("FAIL", timeout=15000)
    page.screenshot(path=str(out_dir / "polycube-parcel-failure.png"), full_page=True)
    after = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    assert after != before
    page.screenshot(path=str(out_dir / "polycube-parcel-recovery.png"), full_page=True)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID, advance=None) -> None:
    del mechanic, advance
    public = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))
    truth = json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))
    interaction = (truth.get("control_condition") or {}).get("interaction", "full")
    camera = dict((truth.get("world") or {}).get("camera") or {"yaw": 0, "pitch": 0.48})
    pieces = {str(piece["id"]): dict(piece) for piece in (truth.get("world") or {}).get("pieces") or []}
    page.screenshot(path=str(out_dir / "polycube-parcel-initial.png"), full_page=True)
    _camera_orbit(page, interaction, camera)
    for piece_id in (truth.get("valid_piece_ids") or []):
        piece = pieces[piece_id]
        if piece.get("locked"):
            continue
        _select(page, piece_id)
        target = truth["solution_placements"][piece_id]
        _rotate(page, piece, target["orientation"])
        if interaction == "simplified":
            _place_simplified(page, piece, target["origin"])
        else:
            _place_full(page, piece, target["cells"], target["origin"], camera)
        page.screenshot(path=str(out_dir / f"polycube-parcel-{piece_id}.png"), full_page=True)
        page.locator(".pp-clear").click()
    page.screenshot(path=str(out_dir / "polycube-parcel-solved.png"), full_page=True)
    page.locator(".pp-submit").click()
    expect(page.locator(".pp-readout")).to_have_attribute("data-status", "passed", timeout=15000)
    page.screenshot(path=str(out_dir / "polycube-parcel-pass.png"), full_page=True)
