#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.tools import record_pending_next_ten_solution_videos as recorder


recorder.MECHANICS = (
    "shadow_crime_lab",
    "trajectory_catcher",
    "jigsaw_slider_alignment",
    "microgame_gauntlet",
    "minecraft_block_grid",
    "relation_prompt_grounding",
    "rorschach_fixed_rubric",
    "single_scene_split_boxes",
    "top_face_dice_arithmetic",
    "trace_shape_without_walls",
    "wizard_critter_capture",
)

recorder.WALKTHROUGHS = {
    "shadow_crime_lab": (
        "Shadow Crime Lab",
        "Move the lamp through four probe stations, track which silhouette remains physically consistent, then drag the released evidence tag onto that rendered shadow.",
    ),
    "trajectory_catcher": (
        "Trajectory Catcher",
        "Observe the ballistic preview, move and orient the full capture tunnel, resize its jaws, then launch so the projectile enters the volume along its axis.",
    ),
    "jigsaw_slider_alignment": (
        "Jigsaw Slider Alignment",
        "Calibrate rail position, optical depth, scale, and orientation while inertia remains live, then hold the three-axis scan stable long enough to lock the fragment.",
    ),
    "microgame_gauntlet": (
        "Five-System Verification Reactor",
        "Preserve one stability budget through an eight-pulse hold, three sequential chords, narrow inertial braking, three moving interceptions, and a tight nine-hoop route.",
    ),
    "minecraft_block_grid": (
        "Minecraft Block Grid",
        "Orbit the voxel structure, infer hidden support and ray geometry, then mine and place all four requested blocks without lava or structural collapse.",
    ),
    "relation_prompt_grounding": (
        "Dual-Projection Sculpture Rig",
        "Carry five objects from a moving carousel, reconcile their live marks with front and side projection seals, calibrate every depth, and anticipate settle drift.",
    ),
    "rorschach_fixed_rubric": (
        "Specimen-Bound Rorschach Lab",
        "Load each ambiguous material card, physically run both generated tests on all five specimens, compare ten transient responses, and stamp the sole composite match.",
    ),
    "single_scene_split_boxes": (
        "Single Scene / Split Boxes",
        "Reconstruct one live scene across nine shards by repairing spatial permutation, 180-degree orientation, and independent time phase, then hold continuous sync.",
    ),
    "top_face_dice_arithmetic": (
        "Four-Die Foundry Arithmetic",
        "Roll four rigid dice through world-relative controls, reconcile their visible orientations, and settle exactly the requested top-face sum across distinct values.",
    ),
    "trace_shape_without_walls": (
        "Trace Shape Without Walls",
        "Actively map a hidden corridor with sparse probes, ignore false echoes, then continuously steer the crosswind-distorted tracer through the discovered path without collision.",
    ),
    "wizard_critter_capture": (
        "Wizard Critter Capture",
        "Memorize the fleeting target sigil, place a lure, use limited freeze energy through cover and portals, then lead a finite-flight net into the moving familiar.",
    ),
}

# Capture-only pacing makes physical gestures visible without changing any task contract.
recorder.PACE = {
    "shadow_crime_lab": {"key_press_ms": 0, "mouse_move_ms": 14},
    "trajectory_catcher": {"key_press_ms": 0, "mouse_move_ms": 14},
    "jigsaw_slider_alignment": {"key_press_ms": 0, "mouse_move_ms": 14},
    "microgame_gauntlet": {"key_press_ms": 10, "mouse_move_ms": 10},
    "minecraft_block_grid": {"key_press_ms": 8, "mouse_move_ms": 8},
    "relation_prompt_grounding": {"key_press_ms": 0, "mouse_move_ms": 12},
    "rorschach_fixed_rubric": {"key_press_ms": 0, "mouse_move_ms": 10},
    "single_scene_split_boxes": {"key_press_ms": 0, "mouse_move_ms": 12},
    "top_face_dice_arithmetic": {"key_press_ms": 8, "mouse_move_ms": 0},
    "trace_shape_without_walls": {"key_press_ms": 0, "mouse_move_ms": 8},
    "wizard_critter_capture": {"key_press_ms": 8, "mouse_move_ms": 8},
}


def _has(option: str) -> bool:
    return option in sys.argv[1:]


def main() -> None:
    if not _has("--out-dir"):
        sys.argv.extend(["--out-dir", str(recorder.BENCH_ROOT / "evidence" / "final_eleven_v1" / "solution_videos")])
    if not _has("--port"):
        sys.argv.extend(["--port", "9520"])
    if not _has("--seed-prefix"):
        sys.argv.extend(["--seed-prefix", "final-eleven-solution-video"])
    recorder.main()


if __name__ == "__main__":
    main()
