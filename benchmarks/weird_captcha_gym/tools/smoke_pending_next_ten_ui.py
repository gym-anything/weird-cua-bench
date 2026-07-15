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
    "bureaucratic_signature_trap",
    "temporal_memory_first_change",
    "polyrhythm_customs",
    "exact_change_candy_cascade",
    "tiny_fps_customs",
    "thirty_year_time_wheel",
    "photograph_eats_the_room",
    "clockwork_doppelganger_customs",
    "recursive_dollhouse_smuggling",
    "flat_prisoner",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise the next ten pending environments with clean passing trajectories.")
    parser.add_argument("--out-dir", default=str(BENCH_ROOT / "evidence" / "pending_next_ten_v2"))
    parser.add_argument("--port", type=int, default=8990)
    parser.add_argument("--seed-prefix", default="pending-next-ten-v2-canonical")
    args = parser.parse_args()
    run_batch(
        mechanics=MECHANICS,
        out_dir=Path(args.out_dir),
        port=args.port,
        seed_prefix=args.seed_prefix,
    )


if __name__ == "__main__":
    main()
