"""Authoritative replay grader for Offcut Foundry."""
from __future__ import annotations

from collections import deque
from typing import Any


MECHANIC_ID = "offcut_foundry"


def _result(passed: bool, feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": passed, "score": 100 if passed else 0, "feedback": feedback}


def _normalise(cells: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not cells:
        return ()
    min_row = min(row for row, _ in cells)
    min_column = min(column for _, column in cells)
    return tuple(sorted((row - min_row, column - min_column) for row, column in cells))


def _connected(cells: set[str], positions: dict[str, tuple[int, int]]) -> bool:
    if not cells:
        return False
    seen = {next(iter(cells))}
    queue = deque(seen)
    while queue:
        current = queue.popleft()
        row, column = positions[current]
        for candidate, (candidate_row, candidate_column) in positions.items():
            if candidate in cells and candidate not in seen and abs(candidate_row - row) + abs(candidate_column - column) == 1:
                seen.add(candidate)
                queue.append(candidate)
    return seen == cells


def _exposed(cells: set[str], active: set[str], positions: dict[str, tuple[int, int]], rows: int, columns: int) -> bool:
    for cell_id in cells:
        row, column = positions[cell_id]
        for candidate_row, candidate_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if candidate_row < 0 or candidate_row >= rows or candidate_column < 0 or candidate_column >= columns:
                return True
            candidate_id = f"cell-{candidate_row:02d}-{candidate_column:02d}"
            if candidate_id not in active:
                return True
    return False


def _cells_from_event(value: Any, positions: dict[str, tuple[int, int]]) -> list[str] | None:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        return None
    if len(set(value)) != len(value) or any(item not in positions for item in value):
        return None
    return value


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    try:
        if truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
            return _result(False, "mechanic identity mismatch")
        for key in ("task_id", "challenge_id"):
            if not truth.get(key) or payload.get(key) != truth.get(key) or public.get(key) != truth.get(key):
                return _result(False, f"stale or mismatched {key}")
        if payload.get("control_condition") != truth.get("control_condition"):
            return _result(False, "wrong control condition")
        if public.get("control_condition") != truth.get("control_condition"):
            return _result(False, "public control condition was altered")
        if public.get("board") != truth.get("board") or public.get("pieces") != truth.get("pieces"):
            return _result(False, "visible board or cut list does not match the generated task")
        if public.get("requirements") != truth.get("requirements"):
            return _result(False, "visible requirements do not match the generated task")

        condition = truth.get("control_condition") or {}
        mode = str(condition.get("interaction") or "full")
        if mode not in {"simplified", "full"}:
            return _result(False, "invalid interaction condition")
        sources = {
            "full": {"cut": "direct_trace", "undo": "direct_undo"},
            "simplified": {
                "piece_select": "proxy_piece_select",
                "select_cell": "proxy_cell",
                "cut": "proxy_extract",
                "undo": "proxy_undo",
            },
        }[mode]
        board = truth["board"]
        rows = int(board["rows"])
        columns = int(board["columns"])
        positions = {
            str(cell["id"]): (int(cell["row"]), int(cell["column"]))
            for cell in board["cells"]
        }
        initial = set(str(cell_id) for cell_id in truth["initial_cells"])
        active = set(initial)
        pieces = {str(piece["id"]): piece for piece in truth["pieces"]}
        placements = {str(key): set(str(item) for item in value) for key, value in truth["placements"].items()}
        shapes = {
            piece_id: _normalise([tuple(map(int, point)) for point in piece["shape"]])
            for piece_id, piece in pieces.items()
        }
        events = payload.get("events")
        if not isinstance(events, list) or not events or len(events) > 5000:
            return _result(False, "invalid or empty cut history")

        selected_piece: str | None = None
        selected_cells: set[str] = set()
        cut_history: list[dict[str, Any]] = []
        cut_pieces: set[str] = set()
        undo_count = 0
        certified = False
        mistakes = 0
        for sequence, event in enumerate(events, start=1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                return _result(False, "cut history sequence is malformed")
            kind = str(event.get("kind") or "")
            if certified:
                return _result(False, "actions occurred after certification")
            if kind == "piece_select":
                if mode != "simplified" or event.get("input_source") != sources[kind]:
                    return _result(False, "wrong interaction surface for piece selection")
                piece_id = str(event.get("piece_id") or "")
                if piece_id not in pieces or piece_id in cut_pieces:
                    return _result(False, "invalid or already cut piece selection")
                selected_piece = piece_id
                selected_cells.clear()
            elif kind == "select_cell":
                if mode != "simplified" or event.get("input_source") != sources[kind]:
                    return _result(False, "wrong interaction surface for cell selection")
                cell_id = str(event.get("cell_id") or "")
                if cell_id not in active:
                    return _result(False, "selected cell is no longer material")
                should_be_selected = bool(event.get("selected"))
                if should_be_selected:
                    selected_cells.add(cell_id)
                else:
                    selected_cells.discard(cell_id)
            elif kind == "cut":
                if event.get("input_source") != sources[kind]:
                    return _result(False, "wrong interaction surface for extraction")
                piece_id = str(event.get("piece_id") or "")
                cells = _cells_from_event(event.get("cells"), positions)
                trace = _cells_from_event(event.get("trace"), positions)
                if piece_id not in pieces or piece_id in cut_pieces or cells is None or trace is None:
                    return _result(False, "malformed or repeated extraction")
                if mode == "simplified" and (selected_piece != piece_id or set(cells) != selected_cells):
                    return _result(False, "proxy extraction differs from the selected cells")
                if mode == "full":
                    if set(trace) != set(cells):
                        return _result(False, "direct trace does not cover the extracted cells")
                    for before, after in zip(trace, trace[1:]):
                        if sum(abs(a - b) for a, b in zip(positions[before], positions[after])) > 1:
                            return _result(False, "direct trace skips across the board")
                cell_set = set(cells)
                if not cell_set <= active:
                    return _result(False, "cut includes spent material")
                if not _connected(cell_set, positions):
                    return _result(False, "cut is not a connected piece")
                if not _exposed(cell_set, active, positions, rows, columns):
                    return _result(False, "cut is sealed inside the remaining workpiece")
                shape = _normalise([positions[cell_id] for cell_id in cells])
                if shape != shapes[piece_id]:
                    return _result(False, "selected cells do not match the requested silhouette")
                correct_location = cell_set == placements[piece_id]
                if not correct_location:
                    mistakes += 1
                active -= cell_set
                cut_pieces.add(piece_id)
                cut_history.append({"piece_id": piece_id, "cells": cell_set, "correct_location": correct_location})
                selected_piece = None
                selected_cells.clear()
            elif kind == "undo":
                if event.get("input_source") != sources[kind]:
                    return _result(False, "wrong interaction surface for undo")
                if not cut_history:
                    return _result(False, "undo has no cut to restore")
                undo_count += 1
                if undo_count > int(truth["requirements"]["undo_budget"]):
                    return _result(False, "undo budget exceeded")
                last_cut = cut_history.pop()
                active.update(last_cut["cells"])
                cut_pieces.discard(last_cut["piece_id"])
                if not last_cut["correct_location"]:
                    mistakes -= 1
                selected_piece = None
                selected_cells.clear()
            elif kind == "certify":
                if event.get("input_source") != "certify_button":
                    return _result(False, "certification did not come from the visible button")
                certified = True
            else:
                return _result(False, f"unknown cut action {kind!r}")

        if not certified:
            return _result(False, "the foundry was not certified")
        expected_piece_ids = set(pieces)
        if cut_pieces != expected_piece_ids:
            return _result(False, f"only {len(cut_pieces)}/{len(expected_piece_ids)} requested offcuts were extracted")
        if active:
            return _result(False, f"{len(active)} cells of material remain")
        if mistakes:
            return _result(False, "a locally legal cut took material from the wrong partition")
        if any(item["correct_location"] is not True for item in cut_history):
            return _result(False, "the final partition does not match the generated board")
        if len(cut_history) != len(expected_piece_ids):
            return _result(False, "the final cut history is incomplete")
        return _result(True, "PASS — every requested offcut was cut once, in connected exposed material, with no waste")
    except (KeyError, TypeError, ValueError, IndexError):
        return _result(False, "malformed Offcut Foundry submission")
