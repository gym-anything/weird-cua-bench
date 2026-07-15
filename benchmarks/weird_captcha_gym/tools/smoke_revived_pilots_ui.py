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
    "moving_checkbox_evasive_button",
    "reverse_identity_gate",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the two fully rebuilt pilots through failure isolation and clean passing browser trajectories."
    )
    parser.add_argument("--out-dir", default=str(BENCH_ROOT / "evidence" / "incubator_batch_revived_v1"))
    parser.add_argument("--port", type=int, default=9410)
    parser.add_argument("--seed-prefix", default="revived-pilots-canonical")
    args = parser.parse_args()
    run_batch(
        mechanics=MECHANICS,
        out_dir=Path(args.out_dir),
        port=args.port,
        seed_prefix=args.seed_prefix,
    )


if __name__ == "__main__":
    main()
