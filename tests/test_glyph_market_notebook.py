from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load("glyph_market_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/glyph_market_notebook.py")
GRADER = load("glyph_market_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/glyph_market_notebook.py")


def task(level: int, mode: str) -> dict:
    return {
        "id": f"glyph_market_notebook_d{level}_{mode}_seed_0001@0.2",
        "_control_condition": {"difficulty": level, "interaction": mode, "real_time": "live", "difficulty_parameters": copy.deepcopy(GENERATOR.PROFILES[level])},
    }


def solved_payload(public: dict, truth: dict, mode: str) -> dict:
    inspect_source = "hotspot_click" if mode == "full" else "inspect_proxy"
    match_source = "drag_match" if mode == "full" else "select_match"
    glyph_for_spot = {
        spot["id"]: spot["glyph_id"]
        for scene in public["world"]["scenes"]
        for spot in scene["spots"]
    }
    events = [
        {"type": "inspect", "spot_id": spot_id, "glyph_id": glyph_for_spot[spot_id], "source": inspect_source}
        for spot_id in truth["required_spots"]
    ]
    annotations = {}
    for index, glyph_id in enumerate(truth["glyph_ids"]):
        note = f"provisional reading {index + 1}"
        annotations[glyph_id] = note
        events.append({"type": "annotate", "glyph_id": glyph_id, "text": note, "source": "notebook_input"})
    assignments = {}
    for page in public["world"]["pages"]:
        assignments[page["id"]] = {}
        for card in page["cards"]:
            glyph_id = truth["mapping"][card["id"]]
            assignments[page["id"]][card["id"]] = glyph_id
            events.append({"type": "match", "page_id": page["id"], "card_id": card["id"], "glyph_id": glyph_id, "source": match_source})
        events.append({"type": "validate_page", "page_id": page["id"], "passed": True})
    return {
        "mechanic_id": truth["mechanic_id"], "task_id": truth["task_id"], "challenge_id": truth["challenge_id"],
        "events": events, "inspected_spot_ids": sorted(truth["required_spots"]), "annotations": annotations,
        "assignments": assignments, "validated_pages": truth["page_ids"], "completed": True,
    }


def test_all_profiles_and_interaction_pairs_are_seeded_and_shared():
    for level in range(1, 6):
        full, full_truth = GENERATOR.generate(task(level, "full"), "matrix-seed")
        simple, simple_truth = GENERATOR.generate(task(level, "simplified"), "matrix-seed")
        assert full["world"] == simple["world"]
        assert full["challenge_id"] == simple["challenge_id"]
        assert full_truth["mapping"] == simple_truth["mapping"]
        assert len(full["world"]["scenes"]) == GENERATOR.PROFILES[level]["scene_count"]
        assert len(full["world"]["glyphs"]) == GENERATOR.PROFILES[level]["glyph_count"]
        assert sum(len(page["cards"]) for page in full["world"]["pages"]) == GENERATOR.PROFILES[level]["glyph_count"]


def test_baseline_matches_level_three_full_world():
    baseline, baseline_truth = GENERATOR.generate({"id": "glyph_market_notebook_seed_0001@0.1"}, "baseline-seed")
    controlled, controlled_truth = GENERATOR.generate(task(3, "full"), "baseline-seed")
    assert baseline["world"] == controlled["world"]
    assert baseline_truth["mapping"] == controlled_truth["mapping"]
    assert baseline_truth["challenge_id"] == controlled_truth["challenge_id"]


def test_grader_replays_both_modes_and_rejects_wrong_surface_or_stale_state():
    for mode in ("full", "simplified"):
        public, truth = GENERATOR.generate(task(3, mode), "grade-seed")
        payload = solved_payload(public, truth, mode)
        result = GRADER.grade(payload, truth, public)
        assert result["passed"] is True, result
        wrong = copy.deepcopy(payload)
        wrong["events"][0]["source"] = "inspect_proxy" if mode == "full" else "hotspot_click"
        assert GRADER.grade(wrong, truth, public)["passed"] is False
        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale-challenge"
        assert GRADER.grade(stale, truth, public)["passed"] is False


def test_grader_rejects_tampered_public_illustration():
    public, truth = GENERATOR.generate(task(3, "full"), "tamper-seed")
    payload = solved_payload(public, truth, "full")
    public["world"]["pages"][0]["cards"][0]["variant"] += 1
    assert GRADER.grade(payload, truth, public)["passed"] is False
