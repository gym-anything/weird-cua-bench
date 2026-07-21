from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable


CAPABILITIES: dict[str, dict[str, str]] = {
    "visual_understanding_grounding": {
        "code": "V",
        "name": "Visual understanding and grounding",
        "short_name": "Visual grounding",
        "description": "Recognizing relevant objects and locating them correctly on the screen.",
        "color": "#63dbec",
    },
    "spatial_reasoning": {
        "code": "S",
        "name": "Spatial reasoning",
        "short_name": "Spatial reasoning",
        "description": "Understanding positions, directions, shapes, distances, and spatial relationships.",
        "color": "#a99eff",
    },
    "temporal_understanding_memory": {
        "code": "T",
        "name": "Temporal understanding and memory",
        "short_name": "Time and memory",
        "description": "Tracking changes, sequences, motion, and hidden information across time.",
        "color": "#ffbd66",
    },
    "reasoning": {
        "code": "R",
        "name": "Reasoning",
        "short_name": "Reasoning",
        "description": "Inferring rules, causes, constraints, and correct solutions from available evidence.",
        "color": "#f0df6f",
    },
    "planning": {
        "code": "P",
        "name": "Planning",
        "short_name": "Planning",
        "description": "Choosing and ordering actions that lead toward the goal.",
        "color": "#ff7f63",
    },
    "interaction_control": {
        "code": "I",
        "name": "Interaction and control",
        "short_name": "Interaction and control",
        "description": "Executing clicks, drags, key presses, holds, trajectories, and corrections accurately.",
        "color": "#d7ff54",
    },
    "adaptation_feedback": {
        "code": "A",
        "name": "Adaptation from feedback",
        "short_name": "Feedback adaptation",
        "description": "Using observed outcomes to revise subsequent actions.",
        "color": "#72e0a4",
    },
}


# Each environment has one primary capability so the public catalog remains
# filterable. Supporting capabilities are included only when the implemented
# interaction makes them materially necessary rather than merely incidental.
CAPABILITY_ASSIGNMENTS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "blind_dice_courier": ("temporal_understanding_memory", ("spatial_reasoning", "planning"), "Maintain a hidden die orientation across rolls and sparse scans."),
    "board_game_captcha": ("interaction_control", ("spatial_reasoning", "temporal_understanding_memory", "adaptation_feedback"), "Continuously control momentum through obstacles and ordered targets."),
    "bomb_manual_from_hell": ("spatial_reasoning", ("visual_understanding_grounding", "reasoning", "interaction_control"), "Register transformed transparent plates to isolate one physical wire."),
    "bureaucratic_signature_trap": ("interaction_control", ("spatial_reasoning", "visual_understanding_grounding"), "Reveal and reproduce a precise continuous path."),
    "clockwork_clutch_safe": ("temporal_understanding_memory", ("interaction_control", "reasoning"), "Time releases across coupled rotating systems."),
    "clockwork_doppelganger_customs": ("temporal_understanding_memory", ("planning", "interaction_control", "reasoning"), "Synchronize recorded action loops on one shared timeline."),
    "code_to_diagram_captcha": ("temporal_understanding_memory", ("reasoning", "planning", "interaction_control"), "Remember transient branches before reconstructing the control-flow graph."),
    "consequences_boss": ("temporal_understanding_memory", ("spatial_reasoning",), "Reconstruct previously created states after occlusion and shuffling."),
    "craftcha_alchemy_bench": ("planning", ("temporal_understanding_memory", "reasoning", "interaction_control"), "Execute a remembered multi-stage recipe with finite resources."),
    "crash_deadline_hovercar": ("interaction_control", ("temporal_understanding_memory", "visual_understanding_grounding", "spatial_reasoning"), "Steer continuously while tracking moving pointer targets."),
    "cursor_constellation_hunt": ("visual_understanding_grounding", ("interaction_control",), "Actively search for a cursor-conditioned visual target."),
    "cursor_lens_reveal": ("visual_understanding_grounding", ("temporal_understanding_memory", "interaction_control", "adaptation_feedback"), "Find moving echoes through active lens settings and sustained holds."),
    "dead_mans_switch": ("interaction_control", ("temporal_understanding_memory", "spatial_reasoning", "planning"), "Maintain continuous pointer contact while navigating by keyboard."),
    "domino_autopsy": ("adaptation_feedback", ("reasoning", "spatial_reasoning", "planning", "interaction_control"), "Test a physical chain and repair it from observed failures."),
    "elastic_membrane_sorter": ("interaction_control", ("adaptation_feedback", "spatial_reasoning", "reasoning"), "Indirectly control marble motion through a deformable surface."),
    "exact_change_candy_cascade": ("planning", ("reasoning", "temporal_understanding_memory"), "Plan swaps whose cascades produce an exact future score."),
    "exit_vim_terminal_escape": ("planning", ("temporal_understanding_memory", "interaction_control", "reasoning"), "Manage modal state through a long ordered keyboard procedure."),
    "fake_desktop_automation_inversion": ("spatial_reasoning", ("interaction_control", "temporal_understanding_memory", "planning", "adaptation_feedback"), "Control a cursor under changing coordinate transformations."),
    "flat_pack_compliance": ("spatial_reasoning", ("planning", "interaction_control", "reasoning", "adaptation_feedback"), "Construct a geometrically valid assembly that survives physical testing."),
    "flat_prisoner": ("spatial_reasoning", ("planning", "interaction_control", "reasoning"), "Create screen-space connections through perspective before traversal."),
    "floodgate_archive_rescue": ("planning", ("reasoning", "spatial_reasoning", "adaptation_feedback", "interaction_control"), "Sequence water transfers while respecting physical constraints."),
    "forced_perspective_moving_day": ("spatial_reasoning", ("planning", "reasoning", "interaction_control"), "Manipulate apparent size through perspective to alter world geometry."),
    "funeral_ritual": ("reasoning", ("adaptation_feedback", "visual_understanding_grounding", "planning", "interaction_control"), "Discover an unstated sequence through affordances and feedback."),
    "gravity_room_freight": ("planning", ("spatial_reasoning", "reasoning", "interaction_control", "adaptation_feedback"), "Sequence room rotations to route a persistent physical object."),
    "hologram_silhouette_foundry": ("spatial_reasoning", ("reasoning", "visual_understanding_grounding", "interaction_control"), "Construct one 3D object from three required projections."),
    "impossible_ecology": ("interaction_control", ("adaptation_feedback", "spatial_reasoning", "reasoning", "planning"), "Control several agents through coupled global fields."),
    "impossible_panorama": ("visual_understanding_grounding", ("temporal_understanding_memory", "interaction_control", "spatial_reasoning"), "Search a large dynamic scene and maintain a qualified capture."),
    "input_lag_forklift": ("planning", ("temporal_understanding_memory", "spatial_reasoning", "interaction_control", "adaptation_feedback"), "Plan Sokoban actions under a one-command execution delay."),
    "insider_trading_captcha": ("planning", ("temporal_understanding_memory", "reasoning", "adaptation_feedback"), "Plan delayed orders against a changing market trajectory."),
    "jigsaw_slider_alignment": ("spatial_reasoning", ("interaction_control", "visual_understanding_grounding", "temporal_understanding_memory", "adaptation_feedback"), "Align position, depth, scale, and orientation under inertia."),
    "lidar_blacksite": ("spatial_reasoning", ("visual_understanding_grounding", "planning", "interaction_control", "adaptation_feedback"), "Build spatial knowledge through active sensing before navigation."),
    "magnetic_stripe_purgatory": ("adaptation_feedback", ("interaction_control", "temporal_understanding_memory", "spatial_reasoning"), "Discover hidden swipe requirements from speed and direction feedback."),
    "marionette_checkpoint": ("interaction_control", ("spatial_reasoning", "temporal_understanding_memory", "adaptation_feedback"), "Control coupled strings to maintain several simultaneous poses."),
    "microgame_gauntlet": ("interaction_control", ("temporal_understanding_memory", "spatial_reasoning", "visual_understanding_grounding"), "Perform varied holds, chords, braking, interception, and tracing tasks."),
    "minecraft_block_grid": ("spatial_reasoning", ("visual_understanding_grounding", "planning", "interaction_control", "reasoning"), "Reason across camera views to expose safe removable voxels."),
    "modifier_stack_image_grid": ("reasoning", ("temporal_understanding_memory", "planning", "interaction_control", "visual_understanding_grounding"), "Infer and apply the inverse of a transient transformation sequence."),
    "motion_only_ghost_jigsaw": ("visual_understanding_grounding", ("temporal_understanding_memory", "spatial_reasoning", "interaction_control"), "Perceive an image available only through motion before assembly."),
    "moving_checkbox_evasive_button": ("interaction_control", ("spatial_reasoning", "planning", "adaptation_feedback", "temporal_understanding_memory"), "Herd a physical object through independently moving portal surfaces."),
    "occlusion_shell_swindle": ("temporal_understanding_memory", ("visual_understanding_grounding", "interaction_control"), "Preserve object identity through occlusion and hidden transfers."),
    "orbital_docking_customs": ("interaction_control", ("spatial_reasoning", "temporal_understanding_memory", "planning", "adaptation_feedback"), "Control position, velocity, and attitude through delayed physical effects."),
    "parallel_grillmaster": ("temporal_understanding_memory", ("interaction_control", "planning", "visual_understanding_grounding"), "Monitor several concurrent processes with narrow timing windows."),
    "pheromone_dispatch": ("planning", ("spatial_reasoning", "reasoning", "interaction_control", "adaptation_feedback"), "Design a continuous route that guides a distributed swarm."),
    "photograph_eats_the_room": ("spatial_reasoning", ("planning", "reasoning", "interaction_control", "adaptation_feedback"), "Transform room geometry through perspective photographs."),
    "polyrhythm_customs": ("temporal_understanding_memory", ("interaction_control", "planning"), "Remember separate rhythms before performing them together."),
    "popup_exorcist": ("adaptation_feedback", ("reasoning", "visual_understanding_grounding", "spatial_reasoning", "interaction_control"), "Discover how the interface reacts before containing the resulting state."),
    "portal_freight_oversized_parcel": ("spatial_reasoning", ("interaction_control", "reasoning", "planning", "adaptation_feedback"), "Reason about linked coordinate frames during physical transfer."),
    "recursive_dollhouse_smuggling": ("spatial_reasoning", ("planning", "interaction_control", "reasoning"), "Move objects through linked projections with changing scale."),
    "relation_prompt_grounding": ("spatial_reasoning", ("visual_understanding_grounding", "interaction_control", "planning", "temporal_understanding_memory"), "Reconcile object placement across two orthogonal projections."),
    "reload_interruption": ("temporal_understanding_memory", ("interaction_control", "planning", "visual_understanding_grounding"), "Remember an action sequence across real-time interruptions."),
    "reverse_identity_gate": ("interaction_control", ("temporal_understanding_memory", "planning", "visual_understanding_grounding", "spatial_reasoning"), "Coordinate sustained actions across several simultaneously active tabs."),
    "ribbon_switchboard": ("interaction_control", ("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory"), "Inspect depth crossings before tracing one exact continuous route."),
    "robot_art_critic": ("adaptation_feedback", ("interaction_control", "reasoning", "planning"), "Revise a drawing from iterative recognition feedback."),
    "rorschach_fixed_rubric": ("reasoning", ("temporal_understanding_memory", "visual_understanding_grounding", "interaction_control", "planning"), "Compare transient experimental responses to identify one specimen."),
    "rotate_wrong_thing_upright": ("spatial_reasoning", ("interaction_control", "visual_understanding_grounding", "adaptation_feedback"), "Recover world orientation through coupled three-axis manipulation."),
    "rotating_keyboard": ("visual_understanding_grounding", ("temporal_understanding_memory", "interaction_control", "spatial_reasoning"), "Ground keys accurately while their coordinate frame rotates."),
    "semantic_drag_drop_absurdity": ("reasoning", ("temporal_understanding_memory", "visual_understanding_grounding", "interaction_control", "adaptation_feedback"), "Infer hidden pairings from transient physical responses."),
    "shadow_crime_lab": ("reasoning", ("spatial_reasoning", "visual_understanding_grounding", "interaction_control"), "Use causal light probes to identify an impossible shadow."),
    "single_scene_split_boxes": ("temporal_understanding_memory", ("spatial_reasoning", "visual_understanding_grounding", "interaction_control", "adaptation_feedback"), "Synchronize spatial placement, orientation, and animation phase."),
    "slime_commute": ("interaction_control", ("temporal_understanding_memory", "spatial_reasoning", "planning", "adaptation_feedback"), "Navigate continuous moving hazards through sustained control."),
    "slot_reel_capture": ("temporal_understanding_memory", ("interaction_control", "visual_understanding_grounding"), "Act during brief target-specific temporal windows."),
    "specular_lighthouse_relay": ("spatial_reasoning", ("interaction_control", "reasoning", "adaptation_feedback", "temporal_understanding_memory"), "Steer a reflected beam through several coupled mirrors."),
    "surreal_apple_on_tree_grid": ("visual_understanding_grounding", ("spatial_reasoning", "interaction_control", "reasoning"), "Use viewpoint changes to distinguish real depth connections."),
    "temporal_memory_first_change": ("temporal_understanding_memory", ("visual_understanding_grounding", "interaction_control"), "Remember the earliest transient change through later occlusion and shuffling."),
    "thirty_year_time_wheel": ("interaction_control", ("temporal_understanding_memory", "planning", "spatial_reasoning", "adaptation_feedback"), "Manage angular momentum before locking an exact calendar state."),
    "three_camera_claw_machine": ("spatial_reasoning", ("interaction_control", "temporal_understanding_memory", "visual_understanding_grounding", "planning", "adaptation_feedback"), "Triangulate delayed projections for six-axis physical manipulation."),
    "tiny_fps_customs": ("interaction_control", ("visual_understanding_grounding", "spatial_reasoning", "planning", "temporal_understanding_memory"), "Navigate and act precisely while distinguishing protected lookalikes."),
    "tomographic_baggage_surgery": ("spatial_reasoning", ("visual_understanding_grounding", "interaction_control", "reasoning", "planning"), "Reconstruct a hidden volume from slices before collision-free extraction."),
    "top_face_dice_arithmetic": ("temporal_understanding_memory", ("spatial_reasoning", "reasoning", "planning", "interaction_control", "visual_understanding_grounding"), "Track hidden die orientations while routing toward a target sum."),
    "trace_shape_without_walls": ("interaction_control", ("visual_understanding_grounding", "spatial_reasoning", "temporal_understanding_memory", "adaptation_feedback"), "Map a hidden corridor before completing a continuous corrected trace."),
    "trajectory_catcher": ("temporal_understanding_memory", ("spatial_reasoning", "interaction_control", "reasoning", "visual_understanding_grounding"), "Predict motion through occlusion before placing an oriented catcher."),
    "wind_tunnel_seed_courier": ("adaptation_feedback", ("interaction_control", "spatial_reasoning", "planning", "reasoning"), "Correct local forces from observed trajectory feedback."),
    "wizard_critter_capture": ("temporal_understanding_memory", ("spatial_reasoning", "planning", "interaction_control", "visual_understanding_grounding"), "Track identity and motion through cover before delayed interception."),
    "wonky_text_hostile_rendering": ("visual_understanding_grounding", ("spatial_reasoning", "interaction_control", "adaptation_feedback"), "Register several distorted visual layers through continuous adjustment."),
    "wrong_number": ("adaptation_feedback", ("interaction_control", "temporal_understanding_memory", "visual_understanding_grounding", "reasoning"), "Explore signal settings and sustain the only stable carrier lock."),
    "zero_g_cable_autopsy": ("interaction_control", ("spatial_reasoning", "planning", "adaptation_feedback", "visual_understanding_grounding"), "Perform precise bimanual manipulation under continuous physical constraints."),
}


def capability_definitions(primary_counts: Counter[str] | None = None) -> list[dict[str, Any]]:
    counts = primary_counts or Counter()
    return [
        {"id": capability_id, **deepcopy(definition), "primary_count": int(counts[capability_id])}
        for capability_id, definition in CAPABILITIES.items()
    ]


def capability_record(mechanic_id: str) -> dict[str, Any] | None:
    assignment = CAPABILITY_ASSIGNMENTS.get(mechanic_id)
    if assignment is None:
        return None
    primary, supporting, rationale = assignment
    return {
        "primary": primary,
        "supporting": list(supporting),
        "rationale": rationale,
        "status": "working_annotation",
    }


def validate_capability_assignments(mechanic_ids: Iterable[str]) -> None:
    expected = set(mechanic_ids)
    assigned = set(CAPABILITY_ASSIGNMENTS)
    missing = sorted(expected - assigned)
    unexpected = sorted(assigned - expected)
    if missing or unexpected:
        raise ValueError(f"capability assignment mismatch: missing={missing}, unexpected={unexpected}")
    valid_ids = set(CAPABILITIES)
    for mechanic_id, (primary, supporting, rationale) in CAPABILITY_ASSIGNMENTS.items():
        if primary not in valid_ids:
            raise ValueError(f"unknown primary capability for {mechanic_id}: {primary}")
        if not rationale.strip():
            raise ValueError(f"empty capability rationale for {mechanic_id}")
        if primary in supporting or len(supporting) != len(set(supporting)):
            raise ValueError(f"duplicate capability assignment for {mechanic_id}")
        unknown = sorted(set(supporting) - valid_ids)
        if unknown:
            raise ValueError(f"unknown supporting capabilities for {mechanic_id}: {unknown}")


__all__ = [
    "CAPABILITIES",
    "CAPABILITY_ASSIGNMENTS",
    "capability_definitions",
    "capability_record",
    "validate_capability_assignments",
]
