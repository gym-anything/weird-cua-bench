"""Independent transcript replay for Last Seats in the Lagoon."""

from __future__ import annotations

import copy
from typing import Any


MECHANIC_ID = "last_seats_in_the_lagoon"
DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def _shape(orientation: str) -> tuple[int, int]:
    return (2, 1) if orientation == "horizontal" else (1, 2)


def _cells(boat: dict[str, Any], anchor: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    x, y = anchor or (int(boat["x"]), int(boat["y"]))
    width, height = _shape(str(boat.get("orientation")))
    return {(x + dx, y + dy) for dx in range(width) for dy in range(height)}


def _rope_cells(boat: dict[str, Any]) -> set[tuple[int, int]]:
    x, y = int(boat["x"]), int(boat["y"])
    if str(boat.get("orientation")) == "horizontal":
        return {(x, y - 1), (x + 1, y - 1), (x, y + 1), (x + 1, y + 1)}
    return {(x - 1, y), (x - 1, y + 1), (x + 1, y), (x + 1, y + 1)}


def _candidate_clear(
    boat: dict[str, Any],
    target: tuple[int, int],
    boats: list[dict[str, Any]],
    reefs: set[tuple[int, int]],
    columns: int,
    rows: int,
) -> bool:
    footprint = _cells(boat, target)
    if any(x < 0 or y < 0 or x >= columns or y >= rows for x, y in footprint):
        return False
    if footprint & reefs:
        return False
    boat_id = str(boat["id"])
    return all(
        not (footprint & _cells(other))
        for other in boats
        if str(other["id"]) != boat_id
    )


def _replay_move(
    boats: list[dict[str, Any]],
    passengers: list[dict[str, Any]],
    event: dict[str, Any],
    reefs: set[tuple[int, int]],
    columns: int,
    rows: int,
) -> tuple[bool, list[str], str]:
    boat_id = str(event.get("boat_id") or "")
    direction = str(event.get("direction") or "")
    boat = next((item for item in boats if str(item.get("id")) == boat_id), None)
    if boat is None or direction not in DIRS:
        return False, [], "unknown boat or direction"
    before = event.get("from")
    expected_before = [int(boat["x"]), int(boat["y"])]
    if before is not None and before != expected_before:
        return False, [], "event starts from a stale boat position"
    dx, dy = DIRS[direction]
    target = (int(boat["x"]) + dx, int(boat["y"]) + dy)
    if not _candidate_clear(boat, target, boats, reefs, columns, rows):
        return False, [], "boat crossed a reef, boundary, or another boat"
    boat["x"], boat["y"] = target
    expected_after = [target[0], target[1]]
    if event.get("to") is not None and event.get("to") != expected_after:
        return False, [], "event destination does not match the one-cell move"
    occupants = boat.setdefault("occupants", [])
    free = int(boat["capacity"]) - len(occupants)
    boarded: list[str] = []
    contacts = _rope_cells(boat)
    for passenger in sorted(passengers, key=lambda item: str(item["id"])):
        if passenger.get("boarded") or free <= 0:
            continue
        if tuple(passenger.get("position") or ()) not in contacts:
            continue
        passenger["boarded"] = True
        passenger["boat_id"] = boat_id
        passenger["seat"] = len(occupants)
        occupants.append(str(passenger["id"]))
        free -= 1
        boarded.append(str(passenger["id"]))
    reported = event.get("boarded")
    if reported is not None and (not isinstance(reported, list) or reported != boarded):
        return False, boarded, "automatic pickup ledger disagrees with the visible move"
    return True, boarded, "accepted"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(value, dict) for value in (payload, ground_truth, public_state)):
        return _fail("malformed rescue result or task state")
    if ground_truth.get("mechanic_id") != MECHANIC_ID or public_state.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic identity mismatch")
    for key in ("task_id", "challenge_id"):
        if not ground_truth.get(key) or payload.get(key) != ground_truth.get(key) or public_state.get(key) != ground_truth.get(key):
            return _fail(f"stale or mismatched {key}")
    public_keys = (
        "mechanic_id", "task_id", "challenge_id", "prompt", "stage", "board",
        "boats", "passengers", "reefs", "rules", "palette", "generator", "asset_manifest",
        "control_condition",
    )
    if any(public_state.get(key) != ground_truth.get(key) for key in public_keys):
        return _fail("public lagoon world does not match the authoritative task")
    condition = ground_truth.get("control_condition") or {}
    mode = str(condition.get("interaction") or "full")
    expected_source = "drag" if mode == "full" else "direction_buttons"
    if mode not in {"full", "simplified"}:
        return _fail("invalid interaction condition")
    if payload.get("interaction_mode", mode) != mode:
        return _fail("result used the wrong interaction mode")
    if payload.get("completed") is not True:
        return _fail("rescue was not certified as complete")
    events = payload.get("actions")
    if not isinstance(events, list) or not events or len(events) > 600:
        return _fail("missing or overlong boat transcript")
    boats = copy.deepcopy(ground_truth.get("initial_boats") or [])
    passengers = copy.deepcopy(ground_truth.get("initial_passengers") or [])
    if not boats or not passengers:
        return _fail("authoritative lagoon has no boats or passengers")
    columns = int((ground_truth.get("board") or {}).get("columns") or 0)
    rows = int((ground_truth.get("board") or {}).get("rows") or 0)
    reefs = {tuple(item) for item in ground_truth.get("reefs") or []}
    replayed = 0
    for event in events:
        if not isinstance(event, dict):
            return _fail("malformed boat action")
        if event.get("input_source") != expected_source:
            return _fail("transcript used the other interaction surface")
        if event.get("accepted") is False:
            return _fail("a rejected boat movement was submitted")
        accepted, _boarded, message = _replay_move(boats, passengers, event, reefs, columns, rows)
        if not accepted:
            return _fail(message)
        replayed += 1
    if not all(passenger.get("boarded") for passenger in passengers):
        return _fail(
            f"only {sum(bool(item.get('boarded')) for item in passengers)}/{len(passengers)} passengers boarded"
        )
    if any(len(boat.get("occupants") or []) > int(boat.get("capacity") or 0) for boat in boats):
        return _fail("a lifeboat exceeded its seat capacity")
    final = payload.get("final", {})
    if not isinstance(final, dict):
        return _fail("malformed final rescue state")
    if final:
        if final.get("boats") is not None:
            final_boats = final["boats"]
            if not isinstance(final_boats, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or type(item.get("x")) is not int
                or type(item.get("y")) is not int
                for item in final_boats
            ):
                return _fail("malformed final boat positions")
            observed = {item["id"]: [item["x"], item["y"]] for item in final_boats}
            expected = {str(item["id"]): [int(item["x"]), int(item["y"])] for item in boats}
            if len(final_boats) != len(expected) or observed != expected:
                return _fail("final boat positions do not match replay")
        if final.get("boarded") is not None:
            if not isinstance(final["boarded"], list) or any(not isinstance(item, str) for item in final["boarded"]):
                return _fail("malformed final passenger ledger")
            observed_boarded = sorted(final["boarded"])
            expected_boarded = sorted(str(item["id"]) for item in passengers if item.get("boarded"))
            if observed_boarded != expected_boarded:
                return _fail("final passenger ledger does not match replay")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"all {len(passengers)} passengers boarded in {replayed} legal orthogonal moves",
    }
