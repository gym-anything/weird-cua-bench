from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any


BEHAVIOR_NOTES_PATH = Path(__file__).resolve().parent.parent / "docs" / "environment-behavior-notes-v0.md"


CAPABILITIES: dict[str, dict[str, str]] = {
    "visual_understanding_grounding": {
        "code": "V",
        "name": "Visual understanding and grounding",
        "short_name": "Visual grounding",
        "description": "Recognizing relevant visible state and locating it on the screen.",
        "color": "#63dbec",
    },
    "spatial_reasoning": {
        "code": "S",
        "name": "Spatial reasoning",
        "short_name": "Spatial reasoning",
        "description": "Using positions, directions, shapes, distances, or coordinate relationships.",
        "color": "#a99eff",
    },
    "temporal_understanding_memory": {
        "code": "T",
        "name": "Temporal understanding and memory",
        "short_name": "Time and memory",
        "description": "Using motion, order, duration, change, or information that is no longer visible.",
        "color": "#ffbd66",
    },
    "reasoning": {
        "code": "R",
        "name": "Reasoning",
        "short_name": "Reasoning",
        "description": "Inferring a rule, cause, constraint, or solution from available evidence.",
        "color": "#f0df6f",
    },
    "planning": {
        "code": "P",
        "name": "Planning",
        "short_name": "Planning",
        "description": "Choosing and ordering actions whose consequences matter later.",
        "color": "#ff7f63",
    },
    "interaction_control": {
        "code": "I",
        "name": "Interaction and control",
        "short_name": "Interaction and control",
        "description": "Executing a materially constrained click, drag, key sequence, hold, or trajectory.",
        "color": "#d7ff54",
    },
    "adaptation_feedback": {
        "code": "A",
        "name": "Adaptation from feedback",
        "short_name": "Feedback adaptation",
        "description": "Using an observed result to change a later attempt or action.",
        "color": "#72e0a4",
    },
}


REAL_TIME: dict[str, dict[str, str | bool]] = {
    "none": {
        "required": False,
        "label": "No wall-clock requirement",
        "description": "The relevant state can be inspected without a wall-clock deadline.",
    },
    "dynamic_observation": {
        "required": True,
        "label": "Dynamic observation",
        "description": "The required visual evidence is defined by change across wall-clock frames, without a response deadline.",
    },
    "moving_target": {
        "required": True,
        "label": "Moving target",
        "description": "A target changes position while the agent observes or acts.",
    },
    "transient_response": {
        "required": True,
        "label": "Transient response",
        "description": "Relevant visual information is available only during a wall-clock interval.",
    },
    "timed_input": {
        "required": True,
        "label": "Timed input",
        "description": "Acceptance depends on the wall-clock timing or duration of an input.",
    },
    "changing_world": {
        "required": True,
        "label": "Changing world",
        "description": "The task state continues to evolve while the agent observes and acts.",
    },
    "recorded_timing": {
        "required": True,
        "label": "Recorded timing",
        "description": "The agent must produce actions on a wall-clock timeline for later replay.",
    },
}


# The list fixes the dashboard order to the environment-by-environment review.
# Labels describe the easiest passing strategy established by the runtime and
# verifier review. They do not describe every capability that the intended
# puzzle could invite a first-time player to use.
REVIEWED_MECHANICS: tuple[str, ...] = (
    "motion_only_ghost_jigsaw",
    "cursor_constellation_hunt",
    "parallel_grillmaster",
    "rotating_keyboard",
    "slot_reel_capture",
    "domino_autopsy",
    "consequences_boss",
    "popup_exorcist",
    "funeral_ritual",
    "slime_commute",
    "semantic_drag_drop_absurdity",
    "reload_interruption",
    "rotate_wrong_thing_upright",
    "bureaucratic_signature_trap",
    "wonky_text_hostile_rendering",
    "temporal_memory_first_change",
    "surreal_apple_on_tree_grid",
    "cursor_lens_reveal",
    "modifier_stack_image_grid",
    "board_game_captcha",
    "shadow_crime_lab",
    "craftcha_alchemy_bench",
    "occlusion_shell_swindle",
    "ribbon_switchboard",
    "magnetic_stripe_purgatory",
    "trajectory_catcher",
    "impossible_panorama",
    "flat_pack_compliance",
    "crash_deadline_hovercar",
    "robot_art_critic",
    "photograph_eats_the_room",
    "clockwork_doppelganger_customs",
    "recursive_dollhouse_smuggling",
    "flat_prisoner",
    "forced_perspective_moving_day",
    "lidar_blacksite",
    "tomographic_baggage_surgery",
    "three_camera_claw_machine",
    "zero_g_cable_autopsy",
    "portal_freight_oversized_parcel",
    "specular_lighthouse_relay",
    "wind_tunnel_seed_courier",
    "hologram_silhouette_foundry",
    "orbital_docking_customs",
    "gravity_room_freight",
    "floodgate_archive_rescue",
    "elastic_membrane_sorter",
    "pheromone_dispatch",
    "clockwork_clutch_safe",
    "marionette_checkpoint",
    "wrong_number",
    "bomb_manual_from_hell",
    "dead_mans_switch",
    "blind_dice_courier",
    "input_lag_forklift",
)


CAPABILITY_ASSIGNMENTS: dict[str, tuple[tuple[str, ...], str]] = {
    "motion_only_ghost_jigsaw": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "interaction_control"), "dynamic_observation"),
    "cursor_constellation_hunt": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control", "adaptation_feedback"), "none"),
    "parallel_grillmaster": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "transient_response"),
    "rotating_keyboard": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "moving_target"),
    "slot_reel_capture": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "transient_response"),
    "domino_autopsy": (("spatial_reasoning", "reasoning", "planning", "interaction_control"), "none"),
    "consequences_boss": (("temporal_understanding_memory",), "none"),
    "popup_exorcist": (("visual_understanding_grounding", "interaction_control", "adaptation_feedback"), "none"),
    "funeral_ritual": (("visual_understanding_grounding", "planning", "interaction_control"), "none"),
    "slime_commute": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "changing_world"),
    "semantic_drag_drop_absurdity": (("visual_understanding_grounding", "reasoning", "interaction_control"), "timed_input"),
    "reload_interruption": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "changing_world"),
    "rotate_wrong_thing_upright": (("visual_understanding_grounding", "spatial_reasoning", "reasoning", "interaction_control"), "none"),
    "bureaucratic_signature_trap": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "none"),
    "wonky_text_hostile_rendering": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control", "adaptation_feedback"), "none"),
    "temporal_memory_first_change": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "none"),
    "surreal_apple_on_tree_grid": (("visual_understanding_grounding", "interaction_control", "adaptation_feedback"), "none"),
    "cursor_lens_reveal": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control", "adaptation_feedback"), "transient_response"),
    "modifier_stack_image_grid": (("visual_understanding_grounding", "interaction_control", "adaptation_feedback"), "timed_input"),
    "board_game_captcha": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "changing_world"),
    "shadow_crime_lab": (("visual_understanding_grounding", "spatial_reasoning", "reasoning", "interaction_control"), "none"),
    "craftcha_alchemy_bench": (("visual_understanding_grounding", "reasoning", "planning", "adaptation_feedback"), "none"),
    "occlusion_shell_swindle": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "transient_response"),
    "ribbon_switchboard": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "timed_input"),
    "magnetic_stripe_purgatory": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "timed_input"),
    "trajectory_catcher": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "interaction_control", "adaptation_feedback"), "changing_world"),
    "impossible_panorama": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "transient_response"),
    "flat_pack_compliance": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control", "adaptation_feedback"), "none"),
    "crash_deadline_hovercar": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "changing_world"),
    "robot_art_critic": (("reasoning", "interaction_control"), "timed_input"),
    "photograph_eats_the_room": (("visual_understanding_grounding", "spatial_reasoning", "reasoning", "interaction_control"), "none"),
    "clockwork_doppelganger_customs": (("temporal_understanding_memory", "reasoning", "planning", "interaction_control"), "recorded_timing"),
    "recursive_dollhouse_smuggling": (("visual_understanding_grounding", "spatial_reasoning", "planning", "interaction_control"), "none"),
    "flat_prisoner": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "interaction_control"), "changing_world"),
    "forced_perspective_moving_day": (("visual_understanding_grounding", "spatial_reasoning", "reasoning", "interaction_control"), "timed_input"),
    "lidar_blacksite": (("visual_understanding_grounding", "spatial_reasoning", "planning", "interaction_control"), "none"),
    "tomographic_baggage_surgery": (("visual_understanding_grounding", "spatial_reasoning", "planning", "interaction_control"), "none"),
    "three_camera_claw_machine": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "none"),
    "zero_g_cable_autopsy": (("interaction_control",), "none"),
    "portal_freight_oversized_parcel": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "none"),
    "specular_lighthouse_relay": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "interaction_control"), "moving_target"),
    "wind_tunnel_seed_courier": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "changing_world"),
    "hologram_silhouette_foundry": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "none"),
    "orbital_docking_customs": (("visual_understanding_grounding", "interaction_control"), "none"),
    "gravity_room_freight": (("visual_understanding_grounding", "spatial_reasoning", "planning", "interaction_control"), "none"),
    "floodgate_archive_rescue": (("visual_understanding_grounding", "planning", "interaction_control"), "none"),
    "elastic_membrane_sorter": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "changing_world"),
    "pheromone_dispatch": (("temporal_understanding_memory", "interaction_control"), "changing_world"),
    "clockwork_clutch_safe": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "timed_input"),
    "marionette_checkpoint": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "interaction_control"), "moving_target"),
    "wrong_number": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "moving_target"),
    "bomb_manual_from_hell": (("visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "none"),
    "dead_mans_switch": (("visual_understanding_grounding", "temporal_understanding_memory", "interaction_control"), "moving_target"),
    "blind_dice_courier": (("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "planning", "interaction_control"), "none"),
    "input_lag_forklift": (("visual_understanding_grounding", "spatial_reasoning", "planning", "interaction_control"), "none"),
}


_FIELD_LABELS = {
    "Passing behavior": "passing_behavior",
    "What must be observed": "observation",
    "What must be done": "action",
    "What is actually enforced": "enforced",
}


def capability_definitions() -> list[dict[str, str]]:
    return [{"id": capability_id, **deepcopy(definition)} for capability_id, definition in CAPABILITIES.items()]


def _parse_notes() -> list[dict[str, Any]]:
    text = BEHAVIOR_NOTES_PATH.read_text(encoding="utf-8")
    headings = list(re.finditer(r"(?m)^### (\d+)\. (.+)$", text))
    parsed: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        body_start = heading.end()
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[body_start:body_end]
        fields: dict[str, str] = {}
        for label, key in _FIELD_LABELS.items():
            match = re.search(
                rf"\*\*{re.escape(label)}\.\*\*\s*(.*?)(?=\n\n(?:\*\*|##)|\Z)",
                body,
                flags=re.DOTALL,
            )
            if match:
                fields[key] = " ".join(match.group(1).split())
        parsed.append({
            "number": int(heading.group(1)),
            "title": heading.group(2).strip(),
            **fields,
        })
    return parsed


def build_behavior_reviews() -> dict[str, dict[str, Any]]:
    parsed = _parse_notes()
    if len(parsed) != len(REVIEWED_MECHANICS):
        raise ValueError(
            f"behavior review count mismatch: notes={len(parsed)} mechanics={len(REVIEWED_MECHANICS)}"
        )
    if set(CAPABILITY_ASSIGNMENTS) != set(REVIEWED_MECHANICS):
        missing = sorted(set(REVIEWED_MECHANICS) - set(CAPABILITY_ASSIGNMENTS))
        unexpected = sorted(set(CAPABILITY_ASSIGNMENTS) - set(REVIEWED_MECHANICS))
        raise ValueError(f"capability review mismatch: missing={missing}, unexpected={unexpected}")

    reviews: dict[str, dict[str, Any]] = {}
    for expected_number, (mechanic_id, note) in enumerate(zip(REVIEWED_MECHANICS, parsed), start=1):
        if note["number"] != expected_number:
            raise ValueError(
                f"behavior review order mismatch: expected={expected_number} actual={note['number']}"
            )
        missing_fields = sorted(set(_FIELD_LABELS.values()) - set(note))
        if missing_fields:
            raise ValueError(f"behavior review fields missing for {mechanic_id}: {missing_fields}")
        capabilities, real_time_id = CAPABILITY_ASSIGNMENTS[mechanic_id]
        unknown = sorted(set(capabilities) - set(CAPABILITIES))
        if unknown:
            raise ValueError(f"unknown capabilities for {mechanic_id}: {unknown}")
        if real_time_id not in REAL_TIME:
            raise ValueError(f"unknown real-time status for {mechanic_id}: {real_time_id}")
        reviews[mechanic_id] = {
            **note,
            "capabilities": list(capabilities),
            "real_time": {"id": real_time_id, **deepcopy(REAL_TIME[real_time_id])},
            "status": "implementation_reviewed",
        }
    return reviews


__all__ = [
    "BEHAVIOR_NOTES_PATH",
    "CAPABILITIES",
    "CAPABILITY_ASSIGNMENTS",
    "REAL_TIME",
    "REVIEWED_MECHANICS",
    "build_behavior_reviews",
    "capability_definitions",
]
