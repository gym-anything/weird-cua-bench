from __future__ import annotations

import json
import itertools
from collections import deque
from pathlib import Path
from typing import Callable


MECHANIC_ID = "charter_of_the_nine_cantons"
ActionCycle = Callable[[str, Callable[[], None]], None]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _states(state_dir: Path) -> tuple[dict, dict]:
    return _read(state_dir / "public_state.json"), _read(state_dir / "ground_truth.json")


def _interaction(public: dict) -> str:
    return str((public.get("control_condition") or {}).get("interaction") or "full")


def _drag_inside_parcel(page, parcel_id: str) -> None:
    polygon = page.locator(f'[data-parcel="{parcel_id}"]')
    box = polygon.bounding_box()
    if box is None:
        raise AssertionError(f"parcel {parcel_id} has no visible geometry")
    inset = min(7.0, box["width"] * .18)
    x1 = box["x"] + box["width"] / 2 - inset
    x2 = box["x"] + box["width"] / 2 + inset
    y = box["y"] + box["height"] / 2
    page.mouse.move(x1, y)
    page.mouse.down()
    page.mouse.move(x2, y, steps=7)
    page.mouse.up()


def _drag_across_parcels(page, first_id: str, second_id: str) -> None:
    first = page.locator(f'[data-parcel="{first_id}"]').bounding_box()
    second = page.locator(f'[data-parcel="{second_id}"]').bounding_box()
    if first is None or second is None:
        raise AssertionError(f"parcel pair {first_id}, {second_id} has no visible geometry")
    page.mouse.move(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2)
    page.mouse.down()
    # Deliberately deliver one sparse move. The page must resample the segment
    # and paint both visibly adjacent parcels rather than depending on event rate.
    page.mouse.move(second["x"] + second["width"] / 2, second["y"] + second["height"] / 2)
    page.mouse.up()


def _drag_through_parcels(page, parcel_ids: list[str]) -> None:
    centers = []
    for parcel_id in parcel_ids:
        box = page.locator(f'[data-parcel="{parcel_id}"]').bounding_box()
        if box is None:
            raise AssertionError(f"parcel {parcel_id} has no visible geometry")
        centers.append((box["x"] + box["width"] / 2, box["y"] + box["height"] / 2))
    page.mouse.move(*centers[0])
    page.mouse.down()
    for center in centers[1:]:
        page.mouse.move(*center, steps=8)
    page.mouse.up()


def _required_brush_path(public: dict, truth: dict) -> list[str]:
    initial = public["initial_assignment"]
    target = truth["target_assignment"]
    adjacency = public["adjacency"]
    minimum_changes = int(public["parameters"].get("minimum_brush_changes", 2))
    minimum_path = int(public["parameters"].get("minimum_brush_path", 4))

    def shortest(start: str, end: str, members: set[str]) -> list[str] | None:
        previous: dict[str, str | None] = {start: None}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if current == end:
                path = [current]
                while previous[path[-1]] is not None:
                    path.append(previous[path[-1]])
                return list(reversed(path))
            for neighbor in sorted(adjacency[current]):
                if neighbor in members and neighbor not in previous:
                    previous[neighbor] = current
                    queue.append(neighbor)
        return None

    for canton in range(9):
        members = {parcel_id for parcel_id in target if int(target[parcel_id]) == canton}
        repairs = sorted(parcel_id for parcel_id in members if int(initial[parcel_id]) != canton)
        if len(repairs) < minimum_changes:
            continue
        candidates: list[list[str]] = []
        for chosen in itertools.combinations(repairs, minimum_changes):
            for order in itertools.permutations(chosen):
                for start in sorted(members):
                    path = shortest(start, order[0], members)
                    if path is None:
                        continue
                    for repair in order[1:]:
                        leg = shortest(path[-1], repair, members)
                        if leg is None:
                            break
                        path.extend(leg[1:])
                    changed = {parcel_id for parcel_id in path if int(initial[parcel_id]) != canton}
                    if len(changed) >= minimum_changes and len(set(path)) >= minimum_path:
                        candidates.append(path)
        if candidates:
            return min(candidates, key=lambda path: (len(path), path))
    raise AssertionError(
        f"no brush path repaints {minimum_changes} parcels through {minimum_path} joined parcels"
    )


def _act(action_cycle: ActionCycle | None, label: str, callback: Callable[[], None]) -> None:
    if action_cycle is None:
        callback()
    else:
        action_cycle(label, callback)


def _assign(
    page,
    public: dict,
    parcel_id: str,
    canton: int,
    action_cycle: ActionCycle | None = None,
) -> None:
    if _interaction(public) == "simplified":
        _act(
            action_cycle,
            f"select parcel {parcel_id}",
            lambda: page.locator(f'[data-parcel="{parcel_id}"]').click(),
        )
        _act(
            action_cycle,
            f"assign parcel {parcel_id} to canton {canton}",
            lambda: page.locator(f'[data-canton-action="{canton}"]').click(),
        )
    else:
        _act(
            action_cycle,
            f"select canton {canton}",
            lambda: page.locator(f'[data-canton-action="{canton}"]').click(),
        )
        _act(
            action_cycle,
            f"brush parcel {parcel_id}",
            lambda: _drag_inside_parcel(page, parcel_id),
        )
    page.wait_for_timeout(25)


def fail_once(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str,
    *,
    action_cycle: ActionCycle | None = None,
) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    old_challenge = public["challenge_id"]
    _act(action_cycle, "certify unsolved charter", lambda: page.locator("#cn-certify").click())
    page.locator('.nine-cantons[data-fresh-failure="true"] .cn-verdict.is-fail').wait_for(state="visible")
    page.screenshot(path=str(out_dir / "failed-fresh-charter.png"))
    fresh_public, _fresh_truth = _states(state_dir)
    if fresh_public["challenge_id"] == old_challenge:
        raise AssertionError("failed certification did not generate a fresh charter")


def exercise_local_recovery(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str,
    *,
    action_cycle: ActionCycle | None = None,
) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    parcel_id = public["parcels"][0]["id"]
    if _interaction(public) == "full":
        neighbor_id = public["adjacency"][parcel_id][0]
        occupied = {
            int(public["initial_assignment"][parcel_id]),
            int(public["initial_assignment"][neighbor_id]),
        }
        wrong_canton = next(canton for canton in range(9) if canton not in occupied)
        _act(
            action_cycle,
            f"select recovery canton {wrong_canton}",
            lambda: page.locator(f'[data-canton-action="{wrong_canton}"]').click(),
        )
        _act(
            action_cycle,
            f"sparse brush {parcel_id} through {neighbor_id}",
            lambda: _drag_across_parcels(page, parcel_id, neighbor_id),
        )
    else:
        wrong_canton = (int(public["initial_assignment"][parcel_id]) + 1) % 9
        _assign(page, public, parcel_id, wrong_canton, action_cycle)
    page.screenshot(path=str(out_dir / "reversible-wrong-parcel.png"))
    _act(action_cycle, "undo recovery edit", lambda: page.locator("#cn-undo").click())
    page.screenshot(path=str(out_dir / "undone-same-charter.png"))


def solve(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str,
    *,
    certify: bool = True,
    action_cycle: ActionCycle | None = None,
) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, truth = _states(state_dir)
    current = dict(public["initial_assignment"])
    target = truth["target_assignment"]
    repairs = [(parcel_id, int(wanted)) for parcel_id, wanted in target.items() if int(current[parcel_id]) != int(wanted)]
    halfway = max(1, len(repairs) // 2)
    completed_repairs = 0
    active_frame_captured = False
    if _interaction(public) == "full":
        brush_path = _required_brush_path(public, truth)
        canton = int(target[brush_path[-1]])
        _act(
            action_cycle,
            f"select canton {canton} for required border stroke",
            lambda: page.locator(f'[data-canton-action="{canton}"]').click(),
        )
        _act(
            action_cycle,
            f"brush across {' through '.join(brush_path)}",
            lambda: _drag_through_parcels(page, brush_path),
        )
        for parcel_id in brush_path:
            wanted = int(target[parcel_id])
            if int(current[parcel_id]) != wanted:
                current[parcel_id] = wanted
                completed_repairs += 1
        if completed_repairs >= halfway:
            page.screenshot(path=str(out_dir / "active-boundary-repair.png"))
            active_frame_captured = True
    remaining = [
        (parcel_id, canton) for parcel_id, canton in repairs
        if int(current[parcel_id]) != canton
    ]
    for parcel_id, canton in remaining:
        _assign(page, public, parcel_id, canton, action_cycle)
        current[parcel_id] = canton
        completed_repairs += 1
        if not active_frame_captured and completed_repairs >= halfway:
            page.screenshot(path=str(out_dir / "active-boundary-repair.png"))
            active_frame_captured = True
    page.screenshot(path=str(out_dir / "solved-before-certify.png"))
    if certify:
        _act(action_cycle, "certify solved charter", lambda: page.locator("#cn-certify").click())
        page.locator(".cn-verdict.is-pass").wait_for(state="visible")
