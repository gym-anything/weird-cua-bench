from __future__ import annotations

from typing import Any


MECHANIC_ID = "last_carbon_isles"


def _fail(message: str, *, score: int = 0) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": score, "feedback": message}


def _binding_error(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    for item in (payload, truth, public):
        if str(item.get("mechanic_id") or "") != MECHANIC_ID:
            return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"payload {key} mismatch"
        if str(public.get(key) or "") != expected:
            return f"public {key} mismatch"
    return None


def _condition(truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    condition = truth.get("control_condition")
    if condition is None:
        return {"difficulty": 3, "interaction": "full", "real_time": "live", "difficulty_parameters": truth.get("parameters") or {}}
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from generated contract")
    return condition


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if public.get("regions") != truth.get("regions"):
        raise ValueError("public island geometry or initial state differs from truth")
    if public.get("cards") != truth.get("cards"):
        raise ValueError("public card catalog differs from truth")
    if public.get("research_tracks") != truth.get("research_tracks"):
        raise ValueError("public research deck differs from truth")
    regions = {str(item.get("id") or ""): dict(item) for item in truth.get("regions") or [] if isinstance(item, dict)}
    cards = {str(item.get("id") or ""): dict(item) for item in truth.get("cards") or [] if isinstance(item, dict)}
    if not regions or len(regions) != len(truth.get("regions") or []):
        raise ValueError("island identities are invalid")
    if not cards or len(cards) != len(truth.get("cards") or []):
        raise ValueError("policy identities are invalid")
    tracks = truth.get("research_tracks") or []
    if not isinstance(tracks, list):
        raise ValueError("research deck is invalid")
    return regions, cards, {str(item.get("id")): item for item in public.get("regions") or []}, tracks


def _state_snapshot(regions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        region_id: {"emissions": int(region.get("emissions", 0)), "jobs": int(region.get("jobs", 0))}
        for region_id, region in regions.items()
    }


def _is_solved(regions: dict[str, dict[str, Any]]) -> bool:
    return all(int(region.get("emissions", 0)) <= 0 and int(region.get("jobs", 0)) >= 100 for region in regions.values())


def _declared_integer(event: dict[str, Any], key: str, expected: int) -> bool:
    value = event.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if error := _binding_error(payload, ground_truth, public_state):
        return _fail(error)
    try:
        condition = _condition(ground_truth, public_state)
        regions, cards, _public_regions, tracks = _contract(ground_truth, public_state)
    except Exception as exc:
        return _fail(f"carbon-isles contract is invalid: {exc}")

    parameters = dict(condition.get("difficulty_parameters") or {})
    interaction = str(condition.get("interaction") or "full")
    expected_sources = ("card_click", "region_click") if interaction == "simplified" else ("card_drag", "region_drop")
    initial_ids = [str(item) for item in ground_truth.get("initial_hand_ids") or []]
    if not initial_ids or any(card_id not in cards for card_id in initial_ids):
        return _fail("initial policy hand is invalid")
    if public_state.get("hand") is None or [str(item.get("id") or "") for item in public_state.get("hand") or []] != initial_ids:
        return _fail("public initial hand differs from generated hand")

    budget = int(ground_truth.get("initial_budget") or 0)
    initial_budget = budget
    max_turns = int(ground_truth.get("max_turns") or parameters.get("region_count", len(regions)))
    hand = list(initial_ids)
    used: set[str] = set()
    research_stage = 0
    turns = 0
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > len(regions) + len(tracks) + 3:
        return _fail("policy transcript is missing or outside limits")

    last_elapsed = -1
    final_snapshot: dict[str, Any] | None = None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        elapsed = event.get("elapsed_ms")
        if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < last_elapsed:
            return _fail(f"event {sequence} task clock is invalid")
        last_elapsed = elapsed
        kind = str(event.get("kind") or "")
        if kind == "research":
            if research_stage >= len(tracks):
                return _fail("research was requested after the deck was exhausted")
            if str(event.get("source") or "") != "research_button":
                return _fail("research did not use the visible research control")
            if int(event.get("stage", -1)) != research_stage:
                return _fail(f"research event {sequence} skipped a deck stage")
            offer_ids = {str(item.get("id") or "") for item in tracks[research_stage].get("offers") or []}
            card_id = str(event.get("card_id") or "")
            if card_id not in offer_ids or card_id not in cards:
                return _fail(f"research event {sequence} selected a card outside the visible offers")
            cost = int(tracks[research_stage].get("cost", 0))
            if not _declared_integer(event, "cost", cost):
                return _fail(f"research event {sequence} reported the wrong cost")
            if budget < cost:
                return _fail(f"research event {sequence} exceeded the shared budget")
            budget -= cost
            hand.append(card_id)
            research_stage += 1
            continue
        if kind == "play":
            card_id = str(event.get("card_id") or "")
            region_id = str(event.get("region_id") or "")
            if card_id not in hand or card_id in used:
                return _fail(f"play event {sequence} used a policy not in the current hand")
            if region_id not in regions:
                return _fail(f"play event {sequence} targeted an unknown isle")
            if str(event.get("card_source") or "") != expected_sources[0] or str(event.get("region_source") or "") != expected_sources[1]:
                return _fail(f"play event {sequence} used the wrong interaction surface")
            card = cards[card_id]
            effects = card.get("effects") or {}
            effect = effects.get(region_id)
            if not isinstance(effect, dict):
                return _fail(f"play event {sequence} has no generated effect for its target")
            cost = int(card.get("cost", 0))
            if not _declared_integer(event, "cost", cost):
                return _fail(f"play event {sequence} reported the wrong policy cost")
            if budget < cost:
                return _fail(f"play event {sequence} exceeded the shared budget")
            for requirement in card.get('requirements', []):
                donor = regions.get(requirement['region_id'])
                if donor is None or donor['emissions'] > requirement['emissions'] or donor['jobs'] < requirement['jobs']:
                    return _fail(f"play event {sequence} lacks the donor's clean spare crews")
            before = _state_snapshot(regions)
            budget -= cost
            region = regions[region_id]
            region["emissions"] = max(0, int(region.get("emissions", 0)) + int(effect.get("emissions", 0)))
            region["jobs"] = max(0, min(120, int(region.get("jobs", 0)) + int(effect.get("jobs", 0))))
            for donor_id, transfer in card.get('side_effects', {}).items():
                donor = regions[donor_id]
                donor['jobs'] += int(transfer['jobs'])
                donor['emissions'] += int(transfer['emissions'])
            after = _state_snapshot(regions)
            if event.get("before") is not None and event.get("before") != before:
                return _fail(f"play event {sequence} supplied a false pre-play state")
            if event.get("after") is not None and event.get("after") != after:
                return _fail(f"play event {sequence} supplied a false post-play state")
            hand.remove(card_id)
            used.add(card_id)
            turns += 1
            if turns > max_turns:
                return _fail("the island clock expired before certification")
            continue
        if kind == "finish":
            if sequence != len(events):
                return _fail("certification must be the final transcript event")
            final_snapshot = _state_snapshot(regions)
            if not _is_solved(regions):
                remaining = sum(int(item["emissions"]) for item in regions.values())
                weakest = min(int(item["jobs"]) for item in regions.values())
                return _fail(f"certification rejected: {remaining} smoke remains and the lowest crew level is {weakest}")
            if research_stage != len(tracks):
                return _fail("certification was attempted before the available research stages were resolved")
            break
        return _fail(f"event {sequence} has an unknown kind")

    if final_snapshot is None or not _is_solved(regions):
        return _fail("the transcript never certified a solved archipelago")
    target_ids = {str(item) for item in ground_truth.get("target_card_ids") or []}
    if not target_ids.issubset(used):
        return _fail("not every home policy was applied")
    smoke = sum(int(item["emissions"]) for item in regions.values())
    weakest_jobs = min(int(item["jobs"]) for item in regions.values())
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"all {len(regions)} isles clear; smoke {smoke}; lowest crews {weakest_jobs}; budget remaining {budget}/{initial_budget}",
        "final": final_snapshot,
    }
