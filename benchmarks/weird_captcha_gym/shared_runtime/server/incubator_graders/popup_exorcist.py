from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "popup_exorcist"


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    condition = ground_truth.get("control_condition")
    expected_sources: dict[str, str] | None = None
    if condition is not None:
        if public_state.get("control_condition") != condition:
            return {"graded": True, "passed": False, "feedback": "public control condition differs from containment contract"}
        if str(payload.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
            return {"graded": True, "passed": False, "feedback": "controlled task identity mismatch"}
        interaction = str(condition.get("interaction") or "")
        expected_sources = {
            "simplified": {
                "focus": "window_select",
                "close": "selected_close_button",
                "resist": "selected_close_button",
                "drag": "selected_contain_button",
                "contain": "selected_contain_button",
            },
            "full": {
                "focus": "window_pointer",
                "close": "window_close_button",
                "resist": "window_close_button",
                "drag": "window_drag",
                "contain": "window_drag",
            },
        }.get(interaction)
        if expected_sources is None:
            return {"graded": True, "passed": False, "feedback": "containment interaction condition is invalid"}
    events = payload.get("events")
    if not isinstance(events, list) or not 5 <= len(events) <= 180:
        return {"graded": True, "passed": False, "feedback": "containment transcript is missing or outside limits"}
    originals = set(str(item) for item in ground_truth.get("popup_ids") or [])
    parasite = str(ground_truth.get("parasite_id") or "")
    echoes = set(str(item) for item in ground_truth.get("echo_ids") or [])
    parasite_ids = [str(item) for item in (ground_truth.get("parasite_ids") or [parasite])]
    infection_groups = {
        str(parent): [str(item) for item in group]
        for parent, group in (
            ground_truth.get("infection_groups")
            or {parasite: list(ground_truth.get("echo_ids") or [])}
        ).items()
    }
    containment_stages = list(
        ground_truth.get("containment_stages")
        or [ground_truth.get("containment") or {}]
    )
    stage_batches = [
        [str(item) for item in batch]
        for batch in (
            ground_truth.get("stage_batches")
            or [list(ground_truth.get("popup_ids") or [])]
        )
    ]
    maximum_resistance_strikes = int(ground_truth.get("maximum_resistance_strikes") or 3)
    stage_batch_sets = [set(batch) for batch in stage_batches]
    if (
        not parasite_ids
        or len(set(parasite_ids)) != len(parasite_ids)
        or not set(parasite_ids).issubset(originals)
        or set(infection_groups) != set(parasite_ids)
        or set(item for group in infection_groups.values() for item in group) != echoes
        or len(containment_stages) != len(parasite_ids)
        or len(stage_batches) != len(parasite_ids)
        or any(not batch for batch in stage_batch_sets)
        or set().union(*stage_batch_sets) != originals
        or sum(len(batch) for batch in stage_batch_sets) != len(originals)
        or any(
            batch.intersection(parasite_ids) != {parasite_ids[index]}
            for index, batch in enumerate(stage_batch_sets)
        )
    ):
        return {"graded": True, "passed": False, "feedback": "parasite strain contract is malformed"}
    parent_by_window = {
        window_id: parent
        for parent, group in infection_groups.items()
        for window_id in [parent, *group]
    }
    popup_by_id = {str(item.get("id")): dict(item) for item in public_state.get("popups") or []}
    positions = {
        window_id: [
            int(popup_by_id[window_id].get("x") or 0),
            int(popup_by_id[window_id].get("y") or 0),
        ]
        for window_id in originals
    }
    dimensions = {
        window_id: [
            int(popup_by_id[window_id].get("w") or 0),
            int(popup_by_id[window_id].get("h") or 0),
        ]
        for window_id in originals
    }
    live, infected = set(stage_batch_sets[0]), set()
    provoked: set[str] = set()
    contained_parents: set[str] = set()
    spawn_pending = ""
    stage_pending: int | None = None
    active_stage = 0
    contained = ""
    last_drag: dict[str, list[list[int]]] = {}
    resistance_strikes = 0
    purged = False
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind, window_id = str(event.get("kind") or ""), str(event.get("window_id") or "")
        if spawn_pending and kind != "spawn":
            return {"graded": True, "passed": False, "feedback": "parasite echoes were not recorded immediately"}
        if stage_pending is not None and kind != "stage":
            return {"graded": True, "passed": False, "feedback": "next popup wave was not activated immediately"}
        if kind == "stage":
            stage_index = event.get("stage_index")
            activated_ids = [str(item) for item in event.get("activated_ids") or []]
            if (
                stage_pending is None
                or stage_index != stage_pending
                or event.get("input_source") != "containment_field"
                or activated_ids != stage_batches[stage_pending]
                or live.intersection(activated_ids)
            ):
                return {"graded": True, "passed": False, "feedback": "popup wave activation was forged"}
            live.update(activated_ids)
            active_stage = stage_pending
            stage_pending = None
            continue
        if kind == "focus":
            if expected_sources is not None and event.get("input_source") != expected_sources["focus"]:
                return {"graded": True, "passed": False, "feedback": "window focus used the wrong interaction input"}
            if window_id not in live:
                return {"graded": True, "passed": False, "feedback": "focused window was not live"}
            continue
        if kind == "close":
            if expected_sources is not None and event.get("input_source") != expected_sources["close"]:
                return {"graded": True, "passed": False, "feedback": "window close used the wrong interaction input"}
            if window_id not in live:
                return {"graded": True, "passed": False, "feedback": "closed window was not live"}
            if window_id in parasite_ids and window_id not in provoked:
                provoked.add(window_id)
                infected.add(window_id)
                spawn_pending = window_id
            elif window_id not in infected:
                live.remove(window_id)
            continue
        if kind == "spawn":
            listed = set(str(item) for item in event.get("echo_ids") or [])
            parent = str(event.get("parent_id") or "")
            expected_echoes = set(infection_groups.get(parent) or [])
            if not spawn_pending or parent != spawn_pending or listed != expected_echoes:
                return {"graded": True, "passed": False, "feedback": "parasite echo set was forged"}
            live.update(expected_echoes)
            infected.update(expected_echoes)
            parent_x, parent_y = positions[parent]
            parent_w, parent_h = dimensions[parent]
            for index, echo_id in enumerate(infection_groups[parent]):
                horizontal = (
                    74 + (index // 2) * 22
                    if index % 2
                    else -58 - (index // 2) * 18
                )
                positions[echo_id] = [
                    max(8, min(690 - parent_w, parent_x + horizontal)),
                    max(10, min(365 - parent_h, parent_y + 54 + index * 22)),
                ]
                dimensions[echo_id] = [parent_w, parent_h]
            spawn_pending = ""
            continue
        if kind == "drag":
            if expected_sources is not None and event.get("input_source") != expected_sources["drag"]:
                return {"graded": True, "passed": False, "feedback": "window drag used the wrong interaction input"}
            if window_id not in live:
                return {"graded": True, "passed": False, "feedback": "dragged window was not live"}
            samples = event.get("samples")
            if not isinstance(samples, list) or not samples or len(samples) > 80:
                return {"graded": True, "passed": False, "feedback": "window drag samples are missing"}
            clean = []
            for point in samples:
                if not isinstance(point, list) or len(point) != 2 or not all(isinstance(value, int) for value in point):
                    return {"graded": True, "passed": False, "feedback": "window drag sample is malformed"}
                if clean and math.hypot(point[0] - clean[-1][0], point[1] - clean[-1][1]) > 120:
                    return {"graded": True, "passed": False, "feedback": "window teleported during containment"}
                clean.append(point)
            if expected_sources is not None and expected_sources["drag"] == "window_drag":
                if len(clean) < 2:
                    return {
                        "graded": True,
                        "passed": False,
                        "feedback": "full window drag requires an anchored multi-sample path",
                    }
                expected_start = positions.get(window_id)
                if (
                    expected_start is None
                    or math.hypot(
                        clean[0][0] - expected_start[0],
                        clean[0][1] - expected_start[1],
                    )
                    > 3
                ):
                    return {
                        "graded": True,
                        "passed": False,
                        "feedback": "full window drag was not anchored to the visible window",
                    }
            positions[window_id] = list(clean[-1])
            last_drag[window_id] = clean
            continue
        if kind == "contain":
            if expected_sources is not None and event.get("input_source") != expected_sources["contain"]:
                return {"graded": True, "passed": False, "feedback": "window containment used the wrong interaction input"}
            parent = parent_by_window.get(window_id, "")
            if (
                not parent
                or parent not in provoked
                or parent in contained_parents
                or window_id not in infected
                or window_id not in live
                or window_id not in last_drag
            ):
                return {"graded": True, "passed": False, "feedback": "containment occurred before an infected window was physically discovered"}
            end = positions[window_id]
            width, height = dimensions[window_id]
            cx, cy = end[0] + width / 2, end[1] + height / 2
            well = containment_stages[len(contained_parents)]
            if not (float(well.get("x")) <= cx <= float(well.get("x")) + float(well.get("w")) and float(well.get("y")) <= cy <= float(well.get("y")) + float(well.get("h"))):
                return {"graded": True, "passed": False, "feedback": "infected window did not enter the visible containment well"}
            contained = window_id
            contained_parents.add(parent)
            if len(contained_parents) < len(parasite_ids):
                neutralized = {
                    *stage_batch_sets[active_stage],
                    *infection_groups[parent],
                }
                live.difference_update(neutralized)
                infected.difference_update(neutralized)
                stage_pending = len(contained_parents)
            continue
        if kind == "resist":
            if expected_sources is not None and event.get("input_source") != expected_sources["resist"]:
                return {"graded": True, "passed": False, "feedback": "parasite resistance used the wrong interaction input"}
            if not provoked or window_id not in infected or window_id not in live:
                return {"graded": True, "passed": False, "feedback": "resistance was recorded for a noninfected window"}
            resistance_strikes += 1
            if event.get("strike") is not None and event.get("strike") != resistance_strikes:
                return {"graded": True, "passed": False, "feedback": "resistance strike sequence mismatch"}
            if resistance_strikes >= maximum_resistance_strikes:
                return {"graded": True, "passed": False, "feedback": "maximum parasite resistance reached"}
            continue
        if kind == "purge":
            if (
                purged
                or not contained
                or len(contained_parents) != len(parasite_ids)
                or stage_pending is not None
                or active_stage != len(parasite_ids) - 1
                or str(event.get("contained_id") or "") != contained
            ):
                return {"graded": True, "passed": False, "feedback": "purge was not triggered by the contained parasite"}
            remaining = set(str(item) for item in event.get("remaining_before") or [])
            if remaining != live:
                return {"graded": True, "passed": False, "feedback": "purge inventory did not match the live desktop"}
            live.clear()
            purged = True
            continue
        return {"graded": True, "passed": False, "feedback": f"unknown containment event {kind}"}
    passed = (
        set(parasite_ids) == provoked == contained_parents
        and not spawn_pending
        and stage_pending is None
        and active_stage == len(parasite_ids) - 1
        and bool(contained)
        and purged
        and not live
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"strains provoked={len(provoked)}/{len(parasite_ids)}; "
            f"strains contained={len(contained_parents)}/{len(parasite_ids)}; "
            f"live windows={len(live)}"
        ),
    }
