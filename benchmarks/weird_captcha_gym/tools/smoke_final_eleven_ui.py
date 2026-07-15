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


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise the final nine-pending plus two-revision review cohort.")
    parser.add_argument("--out-dir", default=str(BENCH_ROOT / "evidence" / "final_eleven_v1"))
    parser.add_argument("--port", type=int, default=9410)
    parser.add_argument("--seed-prefix", default="final-eleven-canonical")
    args = parser.parse_args()
    run_batch(mechanics=MECHANICS, out_dir=Path(args.out_dir), port=args.port, seed_prefix=args.seed_prefix)


if __name__ == "__main__":
    main()
