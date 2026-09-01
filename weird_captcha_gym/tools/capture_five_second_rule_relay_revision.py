#!/usr/bin/env python3
"""Capture visible-answer relay evidence in isolated headless Chromium.

The driver parses the two rendered instruction lines to choose both tokens.
Private predicate IDs are read only after the visible choices have been made,
so the capture detects ambiguity instead of bypassing it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright

import audit_five_second_rule_relay_seeds as visible_audit
import capture_five_second_rule_evidence as capture


OUTPUT = capture.EVIDENCE / "relay_revision_browser"
GENERATOR = capture.BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relay_first_seed(level: int) -> str:
    generator = capture.load_module(GENERATOR, f"five_second_relay_seed_l{level}")
    task = capture.read_json(capture.BASE_TASK)
    controls = capture.read_json(capture.CONTROLS)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": "full",
        "real_time": "paused",
        "difficulty_parameters": copy.deepcopy(
            controls["difficulty"][str(level)]["parameters"]
        ),
    }
    for index in range(100):
        seed = f"five-second-relay-revision-l{level}-{index:03d}"
        # The browser's first /state request intentionally rotates the setup
        # challenge to the evaluator-style refresh seed.
        public, _truth = generator.generate(task, f"{seed}:refresh:1")
        if public["rounds"][0]["family"] == "relay_pair":
            return seed
    raise AssertionError(f"could not find a relay-first seed for level {level}")


def dom_overlap_pairs(boxes: dict[str, dict[str, float]]) -> list[list[str]]:
    overlaps = []
    ids = list(boxes)
    for index, left_id in enumerate(ids):
        left = boxes[left_id]
        for right_id in ids[index + 1 :]:
            right = boxes[right_id]
            separated = (
                left["x"] + left["width"] <= right["x"]
                or right["x"] + right["width"] <= left["x"]
                or left["y"] + left["height"] <= right["y"]
                or right["y"] + right["height"] <= left["y"]
            )
            if not separated:
                overlaps.append([left_id, right_id])
    return overlaps


def capture_condition(
    playwright: Any,
    temporary: Path,
    output: Path,
    level: int,
    interaction: str,
    seed: str,
) -> dict[str, Any]:
    label = f"d{level}-{interaction}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = capture.condition_task(temporary, level, interaction, "paused")
    process, port = capture.start_server(task, state_dir, seed)
    profile = temporary / "fresh-profiles" / label
    context = playwright.chromium.launch_persistent_context(
        str(profile),
        headless=True,
        viewport=capture.VIEWPORT,
        device_scale_factor=1,
    )
    page = context.pages[0]
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1",
            wait_until="networkidle",
        )
        expect(page.locator(".five-second-rule")).to_be_visible(timeout=8_000)
        public = capture.read_json(state_dir / "public_state.json")
        truth = capture.read_json(state_dir / "ground_truth.json")
        relay = public["rounds"][0]
        if relay["family"] != "relay_pair":
            raise AssertionError(
                f"selected evidence seed did not render relay first: "
                f"{label} seed={seed} first={relay['family']} current="
                f"{capture.read_json(state_dir / 'current_task.json')}"
            )
        expect(page.locator(".fsr-stage.family-relay_pair")).to_be_visible(timeout=2_000)

        rendered_lines = [
            value.splitlines()[-1].strip()
            for value in page.locator(".fsr-order h2").all_inner_texts()
        ]
        if rendered_lines != relay["instruction"]:
            raise AssertionError(
                f"rendered instructions differ from public state: {rendered_lines!r}"
            )
        first_candidates, second_candidates = visible_audit.visible_candidates(relay)
        if len(first_candidates) != 1 or len(second_candidates) != 1:
            raise AssertionError(
                f"visible relay answer is ambiguous: {first_candidates}, {second_candidates}"
            )

        boxes = {}
        for token in relay["tokens"]:
            box = page.locator(f'[data-token-id="{token["id"]}"]').bounding_box()
            if box is None:
                raise AssertionError(f'{token["id"]} has no rendered geometry')
            boxes[token["id"]] = {key: round(float(value), 3) for key, value in box.items()}
        overlaps = dom_overlap_pairs(boxes)
        if overlaps:
            raise AssertionError(f"rendered relay action boxes overlap: {overlaps}")

        initial_path = output / f"{label}-initial.png"
        first_path = output / f"{label}-first-visible-answer.png"
        page.screenshot(path=str(initial_path))
        attribute = "token-id" if interaction == "full" else "proxy-tap"
        page.locator(f'[data-{attribute}="{first_candidates[0]}"]').click()
        expect(
            page.locator(f'[data-{attribute}="{first_candidates[0]}"].is-armed')
        ).to_be_visible()
        page.screenshot(path=str(first_path))
        page.locator(f'[data-{attribute}="{second_candidates[0]}"]').click()
        expect(page.locator(".fsr-stage.family-relay_pair.is-cleared")).to_be_visible(
            timeout=2_000
        )
        if page.locator(".fsr-verdict.is-fail").is_visible():
            raise AssertionError("visible relay answers were rejected by the browser")
        if first_candidates != [truth["rounds"][0]["predicate"]["first_id"]]:
            raise AssertionError("unique visible first answer differs from private grader ID")
        if second_candidates != [truth["rounds"][0]["predicate"]["second_id"]]:
            raise AssertionError("unique visible second answer differs from private grader ID")
        if errors:
            raise AssertionError(f"browser errors: {errors}")

        return {
            "label": label,
            "difficulty": level,
            "interaction": interaction,
            "seed": seed,
            "challenge_id": public["challenge_id"],
            "world_fingerprint": public["world_fingerprint"],
            "instruction": rendered_lines,
            "visible_first_candidates": first_candidates,
            "visible_second_candidates": second_candidates,
            "private_predicate_checked_after_visible_choice": relay["predicate"],
            "visible_choice_accepted": True,
            "rendered_token_boxes": boxes,
            "rendered_overlap_pairs": overlaps,
            "initial_screenshot": initial_path.name,
            "initial_screenshot_sha256": sha256(initial_path),
            "first_answer_screenshot": first_path.name,
            "first_answer_screenshot_sha256": sha256(first_path),
            "isolation": {
                "headless": True,
                "fresh_temporary_persistent_profile": True,
                "loopback_only": True,
                "existing_browser_profile": False,
                "foreground_application": False,
            },
        }
    finally:
        context.close()
        capture.stop_server(process)


def main() -> int:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    seeds = {level: relay_first_seed(level) for level in (4, 5)}
    records = []
    with tempfile.TemporaryDirectory(prefix="five-second-relay-revision-") as raw:
        temporary = Path(raw)
        with sync_playwright() as playwright:
            for level in (4, 5):
                for interaction in ("full", "simplified"):
                    records.append(
                        capture_condition(
                            playwright,
                            temporary,
                            OUTPUT,
                            level,
                            interaction,
                            seeds[level],
                        )
                    )

    for level in (4, 5):
        pair = [item for item in records if item["difficulty"] == level]
        if len({item["world_fingerprint"] for item in pair}) != 1:
            raise AssertionError(f"interaction changed the generated L{level} relay world")
    summary = {
        "ok": True,
        "environment": "Five-Second Rule",
        "conditions_checked": len(records),
        "levels": [4, 5],
        "interaction_modes": ["full", "simplified"],
        "visible_instruction_parser_used_for_actions": True,
        "private_ids_used_to_choose_actions": False,
        "private_ids_checked_only_after_visible_choices": True,
        "all_visible_answers_unique": True,
        "all_visible_answers_accepted": True,
        "all_rendered_action_boxes_non_overlapping": True,
        "full_simplified_same_world_per_level": True,
        "browser_isolation": {
            "headless": True,
            "fresh_temporary_persistent_profile_per_condition": True,
            "loopback_only": True,
            "existing_browser_profile": False,
            "foreground_application": False,
        },
        "records": records,
    }
    capture.write_json(OUTPUT / "summary.json", summary)
    print(json.dumps({"ok": True, "output": str(OUTPUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
