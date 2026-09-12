"""Seeded illustrated vocabulary induction for Glyph Market Notebook."""
from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "glyph_market_notebook"

PROFILES: dict[int, dict[str, int]] = {
    1: {"scene_count": 2, "glyph_count": 3, "spots_per_scene": 2, "page_count": 1, "cards_per_page": 3},
    2: {"scene_count": 3, "glyph_count": 4, "spots_per_scene": 3, "page_count": 1, "cards_per_page": 4},
    3: {"scene_count": 4, "glyph_count": 6, "spots_per_scene": 3, "page_count": 2, "cards_per_page": 3},
    4: {"scene_count": 5, "glyph_count": 7, "spots_per_scene": 4, "page_count": 3, "cards_per_page": 3},
    5: {"scene_count": 6, "glyph_count": 9, "spots_per_scene": 4, "page_count": 3, "cards_per_page": 3},
}

# The integer art codes select original illustrations in the browser.  Names
# remain here only for the white-box oracle and are never rendered as labels.
ARTS = (
    ("sun", "amber"), ("moon", "indigo"), ("water", "cyan"),
    ("bread", "ochre"), ("leaf", "moss"), ("fish", "coral"),
    ("bell", "brass"), ("key", "violet"), ("fire", "vermilion"),
    ("shell", "pearl"), ("flower", "rose"), ("kite", "sky"),
)
SCENE_NAMES = ("Lantern Arcade", "Blue Tarp Wharf", "The Spice Walk", "Moth Court", "Rainwater Stalls", "The Quiet Green")
SCENE_TONES = ("saffron", "teal", "plum", "terracotta", "sage", "ink")


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _glyph(rng: random.Random, index: int) -> dict[str, Any]:
    # Four strokes make marks that are clearly different but still hand-made.
    strokes: list[list[int]] = []
    for stroke_index in range(3 + (index % 2)):
        x = 18 + rng.randrange(14)
        y = 12 + rng.randrange(20)
        dx = rng.choice((-1, 0, 1))
        dy = rng.choice((-1, 0, 1))
        strokes.append([x, y, x + dx * rng.randrange(7, 14), y + dy * rng.randrange(7, 14)])
    if index % 3 == 0:
        strokes.append([12, 28, 36, 28])
    return {
        "id": f"glyph-{index + 1}-{hashlib.sha256(f'{rng.random()}|glyph|{index}'.encode()).hexdigest()[:7]}",
        "strokes": strokes,
        "ink": ("#8d4f3e", "#3e6f71", "#7b5a92", "#a26b3b", "#416b52")[index % 5],
        "seal": ("dot", "bar", "diamond", "arc")[index % 4],
    }


def _spot_id(seed: str, scene: int, index: int) -> str:
    return f"spot-{scene + 1}-{index + 1}-{hashlib.sha256(f'{seed}|spot|{scene}|{index}'.encode()).hexdigest()[:6]}"


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition") or {})
    level = int(condition.get("difficulty", 3))
    parameters = {**PROFILES[level], **(condition.get("difficulty_parameters") or {})}
    rng = random.Random(_seed_int(str(seed), MECHANIC_ID))
    scene_count = int(parameters["scene_count"])
    glyph_count = int(parameters["glyph_count"])
    spots_per_scene = int(parameters["spots_per_scene"])
    page_count = int(parameters["page_count"])
    cards_per_page = int(parameters["cards_per_page"])
    if glyph_count > len(ARTS) or page_count * cards_per_page < glyph_count:
        raise ValueError("Glyph Market profile cannot fit its lexicon on validation pages")

    glyphs = [_glyph(rng, index) for index in range(glyph_count)]
    concept_order = list(range(glyph_count))
    rng.shuffle(concept_order)
    scene_order = list(range(scene_count))
    rng.shuffle(scene_order)
    scenes: list[dict[str, Any]] = []
    required_spots: list[str] = []
    # Every glyph appears in at least two visually different contexts when
    # possible.  Extra contexts are distributed across the market so a single
    # opening view never contains the whole lexicon.
    occurrence = 0
    for scene_index in range(scene_count):
        spots: list[dict[str, Any]] = []
        for slot in range(spots_per_scene):
            art_index = concept_order[occurrence % glyph_count]
            occurrence += 1
            spot_id = _spot_id(str(seed), scene_index, slot)
            required_spots.append(spot_id)
            spots.append({
                "id": spot_id,
                "glyph_id": glyphs[art_index]["id"],
                "art": art_index,
                "variant": (occurrence + scene_index) % 3,
                "x": 17 + slot * int(62 / max(1, spots_per_scene - 1)) + rng.randint(-4, 4) if spots_per_scene > 1 else 50,
                "y": 40 + rng.randint(-8, 8),
                "rotation": rng.randint(-8, 8),
                "size": 1 + ((scene_index + slot) % 2),
            })
        scenes.append({
            "id": f"scene-{scene_index + 1}",
            "title": SCENE_NAMES[scene_order[scene_index] % len(SCENE_NAMES)],
            "tone": SCENE_TONES[scene_order[scene_index] % len(SCENE_TONES)],
            "stamp": ("DAWN", "TIDE", "SPICE", "MOTH", "RAIN", "GREEN")[scene_order[scene_index] % 6],
            "spots": spots,
        })

    # Page card order is independent of scene order.  Cards are novel
    # illustrations of the same visual concepts, not copies of the clues.
    cards: list[dict[str, Any]] = []
    page_concepts = concept_order[:]
    rng.shuffle(page_concepts)
    for page_index in range(page_count):
        page_cards: list[dict[str, Any]] = []
        for slot in range(cards_per_page):
            concept_index = page_concepts[page_index * cards_per_page + slot] if page_index * cards_per_page + slot < glyph_count else None
            if concept_index is None:
                continue
            card_id = f"card-{page_index + 1}-{slot + 1}-{hashlib.sha256(f'{seed}|card|{page_index}|{slot}'.encode()).hexdigest()[:7]}"
            card = {
                "id": card_id,
                "art": concept_index,
                "variant": (page_index + slot + 2) % 4,
                "rotation": rng.randint(-6, 6),
                "caption_mark": (slot + page_index) % 4,
            }
            page_cards.append(card)
            cards.append(card)

    task_id = str(task.get("id") or "glyph_market_notebook_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}".encode("utf-8")).hexdigest()[:16]
    variant_count = max(1, len(ARTS) * (scene_count * spots_per_scene) * (glyph_count ** 2) * page_count)
    world = {
        "width": 980,
        "height": 560,
        "scenes": scenes,
        "glyphs": glyphs,
        "pages": [{"id": f"page-{i + 1}", "number": i + 1, "cards": [c for c in cards if c["id"].startswith(f"card-{i + 1}-")]} for i in range(page_count)],
        "lexicon_size": glyph_count,
        "required_spot_count": len(required_spots),
    }
    # Truth contains the explicit lexicon and card mapping; the normal UI
    # receives the art and glyph strokes needed to render, never the names.
    mapping = {card["id"]: glyphs[int(card["art"])] ["id"] for card in cards}
    lexicon = {glyphs[i]["id"]: ARTS[i][0] for i in range(glyph_count)}
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Build a small picture-language from the market, then test every page.",
        "submit_label": "VALIDATE NOTEBOOK",
        "asset_manifest": "shared_runtime/assets/provenance/glyph_market_notebook_v0.json",
        "generator": {"name": "glyph_market_notebook_v1", "variant_count": variant_count},
        "world": world,
        "action_hint": "Inspect every marked context, annotate each collected mark, and validate every notebook page.",
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": str(seed),
        "challenge_id": challenge_id,
        "public_world": copy.deepcopy(world),
        "mapping": mapping,
        "lexicon": lexicon,
        "required_spots": required_spots,
        "glyph_ids": [g["id"] for g in glyphs],
        "page_ids": [f"page-{i + 1}" for i in range(page_count)],
        "variant_count": variant_count,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
