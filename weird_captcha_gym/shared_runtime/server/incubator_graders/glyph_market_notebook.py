"""Independent replay grader for Glyph Market Notebook."""
from __future__ import annotations

from typing import Any


MECHANIC_ID = "glyph_market_notebook"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _binding(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    for key in ("mechanic_id", "task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"{key} mismatch"
        if str(public.get(key) or "") != expected:
            return f"public {key} mismatch"
    if truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return "wrong mechanic"
    if public.get("world") != truth.get("public_world"):
        return "public illustration world differs from generated world"
    if public.get("control_condition") != truth.get("control_condition"):
        return "interaction or difficulty condition mismatch"
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    error = _binding(payload, ground_truth, public_state)
    if error:
        return _fail(error)
    condition = ground_truth.get("control_condition") or {}
    mode = str(condition.get("interaction") or "full")
    expected_inspect_source = {"full": "hotspot_click", "simplified": "inspect_proxy"}.get(mode)
    expected_match_source = {"full": "drag_match", "simplified": "select_match"}.get(mode)
    if expected_inspect_source is None or expected_match_source is None:
        return _fail("invalid interaction mode")
    required_spots = {str(value) for value in ground_truth.get("required_spots") or []}
    glyph_ids = {str(value) for value in ground_truth.get("glyph_ids") or []}
    mapping = {str(key): str(value) for key, value in (ground_truth.get("mapping") or {}).items()}
    pages = (public_state.get("world") or {}).get("pages") or []
    page_cards = {str(page.get("id")): {str(card.get("id")) for card in page.get("cards") or []} for page in pages}
    scene_ids = {str(scene.get("id")) for scene in (public_state.get("world") or {}).get("scenes") or []}
    if not required_spots or not glyph_ids or not mapping or not page_cards:
        return _fail("malformed lexicon contract")
    expected_glyph_by_spot: dict[str, str] = {}
    for scene in (public_state.get("world") or {}).get("scenes") or []:
        for spot in scene.get("spots") or []:
            spot_id = str(spot.get("id") or "")
            if spot_id in required_spots:
                expected_glyph_by_spot[spot_id] = str(spot.get("glyph_id") or "")
    if set(expected_glyph_by_spot) != required_spots or not all(value in glyph_ids for value in expected_glyph_by_spot.values()):
        return _fail("spot and glyph contract is malformed")

    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 5000:
        return _fail("missing notebook interaction transcript")
    inspected: set[str] = set()
    annotations: dict[str, str] = {}
    assignments: dict[str, dict[str, str]] = {page_id: {} for page_id in page_cards}
    validated: set[str] = set()
    false_validations = 0
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            return _fail(f"event {index} is not an object")
        event_type = str(event.get("type") or "")
        if event_type == "navigate":
            if str(event.get("scene_id") or "") not in scene_ids:
                return _fail(f"event {index} navigates to an unknown scene")
        elif event_type == "inspect":
            spot_id = str(event.get("spot_id") or "")
            if spot_id not in required_spots or str(event.get("source") or "") != expected_inspect_source:
                return _fail(f"event {index} is not a valid {mode} context inspection")
            expected_glyph = expected_glyph_by_spot[spot_id]
            if str(event.get("glyph_id") or "") != expected_glyph:
                return _fail(f"event {index} reports the wrong glyph for a context")
            inspected.add(spot_id)
        elif event_type == "annotate":
            glyph_id = str(event.get("glyph_id") or "")
            note = str(event.get("text") or "").strip()
            if glyph_id not in glyph_ids or not note or str(event.get("source") or "") != "notebook_input":
                return _fail(f"event {index} is not a valid notebook annotation")
            annotations[glyph_id] = note[:240]
        elif event_type == "match":
            page_id = str(event.get("page_id") or "")
            card_id = str(event.get("card_id") or "")
            glyph_id = str(event.get("glyph_id") or "")
            if page_id not in page_cards or card_id not in page_cards[page_id] or glyph_id not in glyph_ids:
                return _fail(f"event {index} names an unknown validation item")
            if str(event.get("source") or "") != expected_match_source:
                return _fail(f"event {index} uses the wrong matching input surface")
            assignments[page_id][card_id] = glyph_id
        elif event_type == "clear_match":
            page_id = str(event.get("page_id") or "")
            card_id = str(event.get("card_id") or "")
            if page_id not in page_cards or card_id not in page_cards[page_id]:
                return _fail(f"event {index} clears an unknown validation item")
            assignments[page_id].pop(card_id, None)
        elif event_type == "validate_page":
            page_id = str(event.get("page_id") or "")
            if page_id not in page_cards:
                return _fail(f"event {index} validates an unknown page")
            expected_page = {card_id: mapping[card_id] for card_id in page_cards[page_id] if card_id in mapping}
            actual_page = assignments[page_id]
            actual_pass = actual_page == expected_page and len(actual_page) == len(page_cards[page_id])
            if bool(event.get("passed")) != actual_pass:
                return _fail(f"event {index} lies about page validation")
            if actual_pass:
                validated.add(page_id)
            else:
                false_validations += 1
        else:
            return _fail(f"event {index} has an unknown type")

    submitted_inspected = {str(value) for value in (payload.get("inspected_spot_ids") or [])}
    if submitted_inspected != inspected or inspected != required_spots:
        return _fail(f"context exploration incomplete: {len(inspected)}/{len(required_spots)}")
    submitted_annotations = {str(key): str(value).strip() for key, value in (payload.get("annotations") or {}).items()}
    if submitted_annotations != annotations or set(annotations) != glyph_ids or any(not value for value in annotations.values()):
        return _fail(f"notebook annotations incomplete: {len(annotations)}/{len(glyph_ids)}")
    submitted_assignments = payload.get("assignments")
    if submitted_assignments != assignments:
        return _fail("submitted notebook assignments differ from replay")
    if set(validated) != set(page_cards):
        return _fail(f"validation pages incomplete: {len(validated)}/{len(page_cards)}")
    completed = payload.get("completed") is True
    passed = completed and false_validations >= 0 and len(validated) == len(page_cards)
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"explored {len(inspected)}/{len(required_spots)} contexts; annotated {len(annotations)}/{len(glyph_ids)} glyphs; validated {len(validated)}/{len(page_cards)} pages; corrections {false_validations}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "mapping": ground_truth.get("mapping") or {},
        "instruction": "Inspect every marked context, annotate every collected glyph, then match each glyph to its corresponding illustration card on every notebook page.",
    }
