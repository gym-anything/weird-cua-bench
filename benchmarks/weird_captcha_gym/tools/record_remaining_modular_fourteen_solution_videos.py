#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.tools import record_pending_next_ten_solution_videos as recorder


recorder.MECHANICS = (
    "consequences_boss",
    "popup_exorcist",
    "slime_commute",
    "reload_interruption",
    "rotate_wrong_thing_upright",
    "wonky_text_hostile_rendering",
    "surreal_apple_on_tree_grid",
    "cursor_lens_reveal",
    "modifier_stack_image_grid",
    "board_game_captcha",
    "craftcha_alchemy_bench",
    "occlusion_shell_swindle",
    "ribbon_switchboard",
    "magnetic_stripe_purgatory",
)

recorder.WALKTHROUGHS = {
    "consequences_boss": (
        "Consequences Boss",
        "Create five socket-and-seal covenants, survive the storm that hides the ledger, then physically reconstruct each choice in the boss's judgment order.",
    ),
    "popup_exorcist": (
        "Popup Exorcist",
        "Peel back anonymous overlapping windows, expose the retaliating parasite, then drag its live infected echo into containment while the desktop replicates around it.",
    ),
    "slime_commute": (
        "Slime Commute",
        "Cross the fixed-step traffic, rail, and river simulation with discrete inputs while moving logs carry the slime continuously between commands.",
    ),
    "reload_interruption": (
        "Reload Interruption",
        "Memorize the once-only seven-gesture reel, execute every physical lever motion, and recover through two moving overload-spark interruptions without losing the sequence.",
    ),
    "rotate_wrong_thing_upright": (
        "Rotate the Wrong Thing Upright",
        "Reconcile front, side, and top projections while manipulating a coupled tri-axis gimbal whose controls perturb one another until the object is truly world-upright.",
    ),
    "wonky_text_hostile_rendering": (
        "Anamorphic Registration Press",
        "Continuously register three nonlinear color plates, lock each physical impression, and press the resolved composite without entering any OCR answer.",
    ),
    "surreal_apple_on_tree_grid": (
        "Parallax Orchard",
        "Orbit the analytic 3D orchard, distinguish true stem contacts from head-on impostors under parallax, and physically harvest only the persistent attachments.",
    ),
    "cursor_lens_reveal": (
        "Polarized Palimpsest",
        "Tune the local polarizer, scan the plate, then keep five sequential moving echoes inside the lens long enough to fix each one before its trail decays.",
    ),
    "modifier_stack_image_grid": (
        "Kinetic Restoration Press",
        "Remember each transient corruption film, assemble its inverse stack in reverse order, then maintain contact while pulling every artifact through the restoration rail.",
    ),
    "board_game_captcha": (
        "Gyroscopic Tilt Board",
        "Continuously steer the inertial ball with a physical tilt pad, light three gates in order, avoid the wells, and settle inside the final cup.",
    ),
    "craftcha_alchemy_bench": (
        "CRAFTCHA: Alchemy Bench",
        "Memorize the briefly exposed recipe, transform all raw branches through their required stations, assemble the terminal device, and deliver it without exhausting the bench.",
    ),
    "occlusion_shell_swindle": (
        "Occlusion Shell Swindle",
        "Track the carrier through repeated occluded shell shuffles, use only the moving inspection aperture for brief evidence, and preserve identity across every round.",
    ),
    "ribbon_switchboard": (
        "Ribbon Switchboard",
        "Probe the layered crossings to infer over-under topology, then route one continuous live ribbon through the safe corridor without touching a conflicting strand.",
    ),
    "magnetic_stripe_purgatory": (
        "Magnetic-Stripe Purgatory",
        "Calibrate the reader, then reproduce the demanded swipe direction, speed profile, and continuous trajectory closely enough for every physical reader to accept the card.",
    ),
}

# Capture-only pacing makes spatial gestures legible. Timing-sensitive mechanics
# retain their solver's exact waits and receive no additional delay here.
recorder.PACE = {
    "consequences_boss": {"key_press_ms": 0, "mouse_move_ms": 10},
    "popup_exorcist": {"key_press_ms": 0, "mouse_move_ms": 10},
    "slime_commute": {"key_press_ms": 5, "mouse_move_ms": 0},
    "reload_interruption": {"key_press_ms": 0, "mouse_move_ms": 5},
    "rotate_wrong_thing_upright": {"key_press_ms": 0, "mouse_move_ms": 10},
    "wonky_text_hostile_rendering": {"key_press_ms": 0, "mouse_move_ms": 10},
    "surreal_apple_on_tree_grid": {"key_press_ms": 0, "mouse_move_ms": 8},
    "cursor_lens_reveal": {"key_press_ms": 0, "mouse_move_ms": 0},
    "modifier_stack_image_grid": {"key_press_ms": 0, "mouse_move_ms": 6},
    "board_game_captcha": {"key_press_ms": 0, "mouse_move_ms": 0},
    "craftcha_alchemy_bench": {"key_press_ms": 0, "mouse_move_ms": 8},
    "occlusion_shell_swindle": {"key_press_ms": 0, "mouse_move_ms": 8},
    "ribbon_switchboard": {"key_press_ms": 0, "mouse_move_ms": 0},
    "magnetic_stripe_purgatory": {"key_press_ms": 0, "mouse_move_ms": 0},
}


def _has(option: str) -> bool:
    return option in sys.argv[1:]


def main() -> None:
    if not _has("--out-dir"):
        sys.argv.extend(
            [
                "--out-dir",
                str(
                    recorder.BENCH_ROOT
                    / "evidence"
                    / "remaining_modular_fourteen_v1"
                    / "solution_videos"
                ),
            ]
        )
    if not _has("--port"):
        sys.argv.extend(["--port", "9560"])
    if not _has("--seed-prefix"):
        sys.argv.extend(["--seed-prefix", "remaining-modular-fourteen-solution-video"])
    recorder.main()


if __name__ == "__main__":
    main()
