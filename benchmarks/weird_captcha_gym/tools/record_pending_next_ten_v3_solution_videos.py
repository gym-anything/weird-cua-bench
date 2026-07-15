#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.tools import record_pending_next_ten_solution_videos as recorder


recorder.MECHANICS = (
    "forced_perspective_moving_day",
    "lidar_blacksite",
    "tomographic_baggage_surgery",
    "three_camera_claw_machine",
    "zero_g_cable_autopsy",
    "portal_freight_oversized_parcel",
    "code_to_diagram_captcha",
    "exit_vim_terminal_escape",
    "fake_desktop_automation_inversion",
    "impossible_ecology",
)

recorder.WALKTHROUGHS = {
    "forced_perspective_moving_day": (
        "Forced-Perspective Moving Day",
        "Preserve apparent size while changing depth to shrink one prop into a key and enlarge another into a bridge, then physically cross the rebuilt room.",
    ),
    "lidar_blacksite": (
        "LIDAR Blacksite",
        "Build a world-anchored point cloud from several scan stations, navigate the dark occluded facility, carry the beacon, and return without one collision.",
    ),
    "tomographic_baggage_surgery": (
        "Tomographic Baggage Surgery",
        "Rotate and slice the sealed volume, register the probe across two projections, capture the hidden target, and extract it without touching an innocent solid.",
    ),
    "three_camera_claw_machine": (
        "Three-Camera Claw Machine",
        "Reconcile three delayed orthographic feeds, brake the inertial claw around an obstacle cage, recover the marked artifact, and deliver it cleanly.",
    ),
    "zero_g_cable_autopsy": (
        "Zero-G Cable Autopsy",
        "Attach both grippers to a deformable cable, coordinate its constraint-driven motion around pegs and alarm contacts, and thread both endpoints through their rings.",
    ),
    "portal_freight_oversized_parcel": (
        "Portal Freight: Oversized Parcel",
        "Raycast two right-handed portal frames, rotate and push a rigid parcel through split occupancy, then contain it in the generated receiver without collision.",
    ),
    "code_to_diagram_captcha": (
        "Live Control-Flow Wiring Lab",
        "Step four branch-covering probes through transient seven-step traces, remember the erased destinations, then patch all ten directed cords across nine nodes.",
    ),
    "exit_vim_terminal_escape": (
        "Modal Terminal Escape",
        "Navigate three read-only reference buffers, repair six manifest lines through Vim modes, write and quit, then unwind pager, job, SSH, and multiplexer layers in order.",
    ),
    "fake_desktop_automation_inversion": (
        "Fake Desktop / Automation Inversion",
        "Operate a transformed remote cursor through overlapping windows, move two work surfaces, transfer two requested seals in order across three remaps, and arm control.",
    ),
    "impossible_ecology": (
        "Impossible Ecology",
        "Calibrate three global fields, infer five incompatible attraction and repulsion responses, then continuously shepherd every coupled organism into its sanctuary.",
    ),
}

# Capture-only pauses improve legibility. They never modify the frozen task,
# generator, browser mechanic, grader, verifier, or solver contract.
recorder.PACE = {
    "forced_perspective_moving_day": {"key_press_ms": 0, "mouse_move_ms": 12},
    "lidar_blacksite": {"key_press_ms": 0, "mouse_move_ms": 0},
    "tomographic_baggage_surgery": {"key_press_ms": 0, "mouse_move_ms": 12},
    "three_camera_claw_machine": {"key_press_ms": 0, "mouse_move_ms": 0},
    "zero_g_cable_autopsy": {"key_press_ms": 0, "mouse_move_ms": 0},
    "portal_freight_oversized_parcel": {"key_press_ms": 0, "mouse_move_ms": 0},
    "code_to_diagram_captcha": {"key_press_ms": 8, "mouse_move_ms": 10},
    "exit_vim_terminal_escape": {"key_press_ms": 20, "mouse_move_ms": 0},
    "fake_desktop_automation_inversion": {"key_press_ms": 0, "mouse_move_ms": 10},
    "impossible_ecology": {"key_press_ms": 0, "mouse_move_ms": 0},
}


def _has(option: str) -> bool:
    return option in sys.argv[1:]


def main() -> None:
    if not _has("--out-dir"):
        sys.argv.extend([
            "--out-dir",
            str(recorder.BENCH_ROOT / "evidence" / "pending_next_ten_v3" / "solution_videos"),
        ])
    if not _has("--port"):
        sys.argv.extend(["--port", "9350"])
    if not _has("--seed-prefix"):
        sys.argv.extend(["--seed-prefix", "pending-next-ten-v3-solution-video"])
    recorder.main()


if __name__ == "__main__":
    main()
