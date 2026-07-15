#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smoke_incubator_batch_one_ui import BENCH_ROOT, run_batch


MECHANICS = (
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the third audited pending cohort with failure isolation and clean passing trajectories."
    )
    parser.add_argument("--out-dir", default=str(BENCH_ROOT / "evidence" / "pending_next_ten_v3"))
    parser.add_argument("--port", type=int, default=8990)
    parser.add_argument("--seed-prefix", default="pending-next-ten-v3-canonical")
    args = parser.parse_args()
    run_batch(
        mechanics=MECHANICS,
        out_dir=Path(args.out_dir),
        port=args.port,
        seed_prefix=args.seed_prefix,
    )


if __name__ == "__main__":
    main()
